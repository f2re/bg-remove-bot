from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import (
    get_package_by_id, create_order, get_order_by_invoice_id,
    mark_order_paid, get_user_orders
)
from app.services.yookassa import YookassaService
from app.keyboards.user_kb import get_payment_confirmation, get_back_keyboard
from app.utils.validators import validate_package_id

router = Router()


class PaymentStates(StatesGroup):
    waiting_for_payment = State()


@router.callback_query(F.data.startswith("buy_package:"))
async def buy_package_handler(callback: CallbackQuery, state: FSMContext):
    """Handle package purchase request"""
    package_id = int(callback.data.split(":")[1])

    db = get_db()
    async with db.get_session() as session:
        package = await get_package_by_id(session, package_id)

        if not package:
            await callback.answer("❌ Пакет не найден", show_alert=True)
            return

        # Generate unique order ID for YooKassa metadata
        import time
        order_id_str = f"order_{callback.from_user.id}_{int(time.time())}"

        # Create order in database (temporarily without payment_id)
        order = await create_order(
            session,
            telegram_id=callback.from_user.id,
            package_id=package.id,
            invoice_id=order_id_str,
            amount=float(package.price_rub)
        )

        # Create payment via YooKassa
        yookassa = YookassaService()
        payment_info = yookassa.create_payment(
            amount=float(package.price_rub),
            description=f"Покупка пакета: {package.name}",
            order_id=order_id_str,
            user_email=None,  # Can add user email if available
            user_phone=None   # Can add user phone if available
        )

        # Update order with YooKassa payment_id
        order.invoice_id = payment_info["payment_id"]
        await session.commit()

        payment_url = payment_info["confirmation_url"]

        # Save payment data to state
        await state.update_data(
            order_id=order.id,
            package_id=package.id,
            amount=float(package.price_rub),
            payment_id=payment_info["payment_id"]
        )
        await state.set_state(PaymentStates.waiting_for_payment)

        text = (
            f"💎 <b>Покупка пакета: {package.name}</b>\n\n"
            f"📦 Изображений: {package.images_count}\n"
            f"💰 Стоимость: {package.price_rub}₽\n\n"
            "Нажмите кнопку ниже для перехода к оплате.\n\n"
            "После успешной оплаты изображения будут автоматически начислены на ваш баланс."
        )

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_payment_confirmation(payment_url)
        )

    await callback.answer()


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_handler(callback: CallbackQuery, state: FSMContext):
    """Handle payment cancellation"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Оплата отменена.\n\n"
        "Вы можете выбрать другой пакет или вернуться в главное меню.",
        reply_markup=get_back_keyboard()
    )
    await callback.answer()


@router.message(F.text == "💳 Проверить оплату")
async def check_payment_handler(message: Message, state: FSMContext):
    """Handle manual payment check"""
    data = await state.get_data()

    if not data or 'order_id' not in data:
        await message.answer("❌ Активных заказов не найдено.")
        return

    db = get_db()
    async with db.get_session() as session:
        # Get order by ID
        from app.database.models import Order
        from sqlalchemy import select

        result = await session.execute(
            select(Order).where(Order.id == data['order_id'])
        )
        order = result.scalar_one_or_none()

        if not order:
            await message.answer("❌ Заказ не найден.")
            return

        if order.status == "paid":
            await state.clear()
            await message.answer(
                "✅ Оплата подтверждена!\n\n"
                f"💎 На ваш баланс начислено изображений: {data.get('images_count', 0)}"
            )
        else:
            await message.answer(
                "⏳ Оплата еще не подтверждена.\n\n"
                "Обычно это занимает несколько минут. Попробуйте проверить позже."
            )


async def notify_payment_success(bot, order_id: int):
    """
    Send notifications after successful payment

    Args:
        bot: Bot instance
        order_id: Order ID
    """
    from app.database.models import Order, User, Package
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.services.notification_service import NotificationService
    from app.database.crud import get_user_balance

    db = get_db()
    async with db.get_session() as session:
        # Get order with related data
        result = await session.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.user), selectinload(Order.package))
        )
        order = result.scalar_one_or_none()

        if not order:
            return

        # Get user's new balance
        new_balance = await get_user_balance(session, order.user.telegram_id)

        # Notify user
        await NotificationService.notify_user_payment_success(
            bot=bot,
            telegram_id=order.user.telegram_id,
            package_name=order.package.name,
            images_count=order.package.images_count,
            amount=float(order.amount),
            new_balance=new_balance
        )

        # Notify admins
        await NotificationService.notify_admins_new_payment(
            bot=bot,
            user_telegram_id=order.user.telegram_id,
            username=order.user.username,
            package_name=order.package.name,
            images_count=order.package.images_count,
            amount=float(order.amount),
            order_id=order.id
        )


async def process_payment_webhook(notification_data: dict, bot=None) -> bool:
    """
    Process payment webhook from YooKassa

    Args:
        notification_data: Raw notification data from YooKassa webhook
        bot: Optional bot instance for sending notifications

    Returns:
        True if payment was processed successfully
    """
    import logging
    logger = logging.getLogger(__name__)

    # Verify and parse webhook notification
    yookassa = YookassaService()
    payment_info = yookassa.verify_webhook_notification(notification_data)

    if not payment_info:
        logger.error("Invalid webhook notification")
        return False

    # Check if payment is successful
    if payment_info["status"] != "succeeded" or not payment_info["paid"]:
        logger.info(f"Payment {payment_info['payment_id']} status: {payment_info['status']}")
        return False

    payment_id = payment_info["payment_id"]

    # Mark order as paid
    db = get_db()
    async with db.get_session() as session:
        order = await mark_order_paid(session, payment_id)

        if not order:
            logger.error(f"Order not found for payment_id {payment_id}")
            return False

        # Payment successful
        logger.info(f"Payment successful for order {order.id}")

        # Send notifications if bot instance is provided
        if bot:
            try:
                await notify_payment_success(bot, order.id)
            except Exception as e:
                logger.error(f"Failed to send notifications for order {order.id}: {str(e)}")

        return True
