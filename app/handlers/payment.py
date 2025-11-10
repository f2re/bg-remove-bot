from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import (
    get_package_by_id, create_order, get_order_by_invoice_id,
    mark_order_paid, get_user_orders
)
from app.services.robokassa import RobokassaService
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

        # Generate unique invoice ID
        import time
        invoice_id = f"order_{callback.from_user.id}_{int(time.time())}"

        # Create order in database
        order = await create_order(
            session,
            telegram_id=callback.from_user.id,
            package_id=package.id,
            invoice_id=invoice_id,
            amount=float(package.price_rub)
        )

        # Generate payment link
        robokassa = RobokassaService()
        payment_url = robokassa.generate_payment_link(
            order_id=order.id,
            amount=float(package.price_rub),
            description=f"Покупка пакета: {package.name}"
        )

        # Save payment data to state
        await state.update_data(
            order_id=order.id,
            package_id=package.id,
            amount=float(package.price_rub)
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


async def process_payment_webhook(invoice_id: str, out_sum: float, signature: str) -> bool:
    """
    Process payment webhook from Robokassa

    Args:
        invoice_id: Invoice ID
        out_sum: Payment amount
        signature: Payment signature

    Returns:
        True if payment was processed successfully
    """
    # Verify signature
    robokassa = RobokassaService()
    if not robokassa.verify_payment_signature(out_sum, int(invoice_id), signature):
        print(f"Invalid signature for invoice {invoice_id}")
        return False

    # Mark order as paid
    db = get_db()
    async with db.get_session() as session:
        order = await mark_order_paid(session, invoice_id)

        if not order:
            print(f"Order not found for invoice {invoice_id}")
            return False

        # Payment successful
        print(f"Payment successful for order {order.id}")
        return True
