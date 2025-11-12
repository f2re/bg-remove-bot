from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db
from app.database.crud import (
    get_statistics, get_open_tickets, resolve_ticket,
    get_or_create_user, get_user_balance, get_ticket_by_id,
    add_support_message
)
from app.services.notification_service import NotificationService
from app.keyboards.admin_kb import (
    get_admin_menu, get_ticket_actions, get_admin_back, get_admin_cancel
)
from app.utils.decorators import admin_only

router = Router()


class AdminStates(StatesGroup):
    waiting_for_ticket_reply = State()
    waiting_for_user_id = State()
    waiting_for_images_count = State()


@router.message(Command("admin"))
@admin_only
async def admin_panel(message: Message):
    """Show admin panel"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽ ({stats['paid_orders']} заказов)\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_menu())


@router.callback_query(F.data == "admin_refresh")
@admin_only
async def admin_refresh(callback: CallbackQuery):
    """Refresh admin panel"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽ ({stats['paid_orders']} заказов)\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_menu())
    await callback.answer("✅ Обновлено")


@router.callback_query(F.data == "admin_stats")
@admin_only
async def admin_stats(callback: CallbackQuery):
    """Show detailed statistics"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "📊 <b>Детальная статистика</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽\n"
        f"   📦 Оплаченных заказов: {stats['paid_orders']}\n"
        f"   ⏳ Активных заказов: {stats['active_orders']}\n\n"
        f"💬 Открытых обращений: {stats['open_tickets']}\n\n"
        "Используйте другие команды для более детального просмотра."
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin_support")
@admin_only
async def admin_support_tickets(callback: CallbackQuery):
    """Show support tickets"""
    db = get_db()
    async with db.get_session() as session:
        tickets = await get_open_tickets(session)

    if not tickets:
        text = "💬 <b>Обращения в поддержку</b>\n\n❌ Нет открытых обращений"
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_back())
        await callback.answer()
        return

    text = "💬 <b>Обращения в поддержку</b>\n\n"

    for ticket in tickets[:10]:  # Show first 10
        text += (
            f"📝 #{ticket.id} | {ticket.status}\n"
            f"👤 User ID: {ticket.user.telegram_id}\n"
            f"💬 {ticket.message[:100]}...\n"
            f"🕐 {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        )

    text += "\nИспользуйте /ticket <ID> для ответа"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_back())
    await callback.answer()


@router.message(Command("ticket"))
@admin_only
async def view_ticket(message: Message):
    """View specific ticket"""
    try:
        ticket_id = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /ticket <ID>")
        return

    db = get_db()
    async with db.get_session() as session:
        from app.database.models import SupportTicket
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await session.execute(
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id)
            .options(selectinload(SupportTicket.user))
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            await message.answer("❌ Обращение не найдено")
            return

        text = (
            f"📝 <b>Обращение #{ticket.id}</b>\n\n"
            f"👤 От: @{ticket.user.username or 'Unknown'} ({ticket.user.telegram_id})\n"
            f"📅 Создано: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📊 Статус: {ticket.status}\n\n"
            f"💬 <b>Сообщение:</b>\n{ticket.message}"
        )

        if ticket.admin_response:
            text += f"\n\n✅ <b>Ваш ответ:</b>\n{ticket.admin_response}"

        await message.answer(text, parse_mode="HTML", reply_markup=get_ticket_actions(ticket.id))


@router.callback_query(F.data.startswith("admin_reply_ticket:"))
@admin_only
async def admin_reply_ticket(callback: CallbackQuery, state: FSMContext):
    """Start replying to ticket"""
    ticket_id = int(callback.data.split(":")[1])

    await state.update_data(ticket_id=ticket_id)
    await state.set_state(AdminStates.waiting_for_ticket_reply)

    await callback.message.edit_text(
        f"✉️ Ответ на обращение #{ticket_id}\n\n"
        "Напишите ваш ответ пользователю:",
        reply_markup=get_admin_cancel()
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_ticket_reply)
@admin_only
async def process_ticket_reply(message: Message, state: FSMContext):
    """Process ticket reply"""
    data = await state.get_data()
    ticket_id = data.get('ticket_id')

    if not ticket_id:
        await message.answer("❌ Ошибка: ID обращения не найден")
        return

    db = get_db()
    async with db.get_session() as session:
        ticket = await get_ticket_by_id(session, ticket_id)

        if not ticket:
            await message.answer("❌ Обращение не найдено")
            return

        # Add message to conversation
        await add_support_message(
            session,
            ticket_id=ticket_id,
            sender_telegram_id=message.from_user.id,
            message=message.text,
            is_admin=True
        )

        # Also update the admin_response field and resolve
        await resolve_ticket(session, ticket_id, message.from_user.id, message.text)

        # Send notification to user using NotificationService
        await NotificationService.notify_user_support_reply(
            bot=message.bot,
            telegram_id=ticket.user.telegram_id,
            ticket_id=ticket_id,
            admin_username=message.from_user.username,
            message=message.text
        )

        await message.answer(f"✅ Ответ отправлен пользователю (ID: {ticket.user.telegram_id})")

    await state.clear()


@router.message(Command("support_reply"))
@admin_only
async def support_reply_command(message: Message):
    """Reply to support ticket using command: /support_reply <ticket_id> <message>"""
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "❌ <b>Использование:</b>\n"
                "/support_reply &lt;ticket_id&gt; &lt;message&gt;\n\n"
                "<b>Пример:</b>\n"
                "/support_reply 123 Ваш вопрос принят, мы работаем над решением",
                parse_mode="HTML"
            )
            return

        ticket_id = int(parts[1])
        reply_message = parts[2]

    except (IndexError, ValueError):
        await message.answer(
            "❌ <b>Ошибка формата</b>\n\n"
            "Используйте: /support_reply &lt;ticket_id&gt; &lt;message&gt;",
            parse_mode="HTML"
        )
        return

    db = get_db()
    async with db.get_session() as session:
        ticket = await get_ticket_by_id(session, ticket_id)

        if not ticket:
            await message.answer(f"❌ Обращение #{ticket_id} не найдено")
            return

        # Add message to conversation
        await add_support_message(
            session,
            ticket_id=ticket_id,
            sender_telegram_id=message.from_user.id,
            message=reply_message,
            is_admin=True
        )

        # Also update the admin_response field
        await resolve_ticket(session, ticket_id, message.from_user.id, reply_message)

        # Send notification to user
        await NotificationService.notify_user_support_reply(
            bot=message.bot,
            telegram_id=ticket.user.telegram_id,
            ticket_id=ticket_id,
            admin_username=message.from_user.username,
            message=reply_message
        )

        await message.answer(
            f"✅ Ответ отправлен!\n\n"
            f"📝 Тикет: #{ticket_id}\n"
            f"👤 Пользователь: {ticket.user.telegram_id}\n"
            f"💬 Ваш ответ: {reply_message[:100]}{'...' if len(reply_message) > 100 else ''}",
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("admin_close_ticket:"))
@admin_only
async def admin_close_ticket(callback: CallbackQuery):
    """Close ticket without reply"""
    ticket_id = int(callback.data.split(":")[1])

    db = get_db()
    async with db.get_session() as session:
        await resolve_ticket(session, ticket_id, callback.from_user.id, "Закрыто администратором")

    await callback.message.edit_text(
        f"✅ Обращение #{ticket_id} закрыто",
        reply_markup=get_admin_back()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_add_images")
@admin_only
async def admin_add_images_start(callback: CallbackQuery, state: FSMContext):
    """Start adding images to user"""
    await state.set_state(AdminStates.waiting_for_user_id)

    await callback.message.edit_text(
        "➕ <b>Добавить изображения пользователю</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
        reply_markup=get_admin_cancel()
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id)
@admin_only
async def admin_add_images_user_id(message: Message, state: FSMContext):
    """Process user ID for adding images"""
    try:
        user_id = int(message.text)
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите числовое значение.")
        return

    # Check if user exists
    db = get_db()
    async with db.get_session() as session:
        user = await get_or_create_user(session, user_id)

    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.waiting_for_images_count)

    await message.answer(
        f"👤 Пользователь: {user.telegram_id}\n\n"
        "Введите количество изображений для добавления:"
    )


@router.message(AdminStates.waiting_for_images_count)
@admin_only
async def admin_add_images_count(message: Message, state: FSMContext):
    """Process images count for adding"""
    try:
        count = int(message.text)
        if count <= 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Неверное количество. Введите положительное число.")
        return

    data = await state.get_data()
    target_user_id = data.get('target_user_id')

    # Add images by creating a manual order
    db = get_db()
    async with db.get_session() as session:
        from app.database.models import Package, Order, User
        from sqlalchemy import select

        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == target_user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("❌ Пользователь не найден")
            return

        # Create manual package entry
        manual_package = Package(
            name=f"Manual {count} images",
            images_count=count,
            price_rub=0,
            is_active=False
        )
        session.add(manual_package)
        await session.flush()

        # Create paid order
        order = Order(
            user_id=user.id,
            package_id=manual_package.id,
            amount=0,
            status="paid",
            robokassa_invoice_id=f"manual_{user.id}_{int(__import__('time').time())}"
        )
        session.add(order)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Добавлено {count} изображений пользователю {target_user_id}"
    )


@router.callback_query(F.data == "admin_cancel_action")
@admin_only
async def admin_cancel_action(callback: CallbackQuery, state: FSMContext):
    """Cancel admin action"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено",
        reply_markup=get_admin_back()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_menu")
@admin_only
async def admin_menu_callback(callback: CallbackQuery):
    """Return to admin menu"""
    db = get_db()
    async with db.get_session() as session:
        stats = await get_statistics(session)

    text = (
        "🔐 <b>Админ-панель</b>\n\n"
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📸 Обработано изображений: {stats['total_processed']}\n"
        f"   🎁 Бесплатных: {stats['free_images_processed']}\n"
        f"   💎 Платных: {stats['paid_images_processed']}\n"
        f"💰 Выручка: {stats['revenue']:.2f}₽ ({stats['paid_orders']} заказов)\n"
        f"📦 Активных заказов: {stats['active_orders']}\n"
        f"💬 Открытых обращений: {stats['open_tickets']}"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_menu())
    await callback.answer()
