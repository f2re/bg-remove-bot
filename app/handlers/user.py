from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from app.database import get_db
from app.database.crud import (
    get_or_create_user, get_user_balance, decrease_balance,
    update_user_stats, save_processed_image, get_all_packages
)
from app.keyboards.user_kb import (
    get_main_menu, get_packages_keyboard, get_info_menu, get_back_keyboard,
    get_support_contact_keyboard, get_buy_package_keyboard, get_low_balance_keyboard
)
from app.services.image_processor import ImageProcessor
from app.services.prompt_builder import PromptBuilder
from app.services.openrouter import OpenRouterService
from app.config import settings
from app.utils.decorators import error_handler

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message):
    """Handle /start command"""
    db = get_db()
    async with db.get_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            free_images_count=settings.FREE_IMAGES_COUNT
        )

    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я — AI-бот для удаления фона с изображений. "
        "Превращаю любое фото в изображение с прозрачным или белым фоном!\n\n"
        f"🎁 У вас {settings.FREE_IMAGES_COUNT} бесплатные обработки!\n\n"
        "📸 <b>Два способа обработки:</b>\n\n"
        "1️⃣ <b>Как Фото</b> (обычная отправка)\n"
        "   • Быстрая обработка\n"
        "   • Результат: на белом фоне\n"
        "   • Для быстрого использования\n\n"
        "2️⃣ <b>Как Документ</b> (📎 → файл)\n"
        "   • Без потери качества\n"
        "   • Результат: PNG с прозрачным фоном\n"
        "   • Для профессионального использования\n\n"
        "💡 <b>Используйте меню ниже:</b>\n"
        "• 📸 Обработать изображение — начать работу\n"
        "• 📊 Мой баланс — проверить доступные обработки\n"
        "• 💎 Купить пакет — пополнить баланс\n"
        "• ℹ️ Информация — узнать детали\n"
        "• 💬 Поддержка — связаться с нами\n\n"
        "✨ Готов к работе! Отправляйте фото!"
    )

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu())


@router.message(F.text == "📊 Мой баланс")
async def balance_handler(message: Message):
    """Handle balance request"""
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, message.from_user.id)

    text = (
        "📊 <b>Ваш баланс:</b>\n\n"
        f"🎁 Бесплатных изображений: {balance['free']}\n"
        f"💎 Оплаченных изображений: {balance['paid']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📸 Всего доступно: {balance['total']}"
    )

    # Add contextual messages and keyboards based on balance
    if balance['total'] == 0:
        text += "\n\n💰 У вас закончились изображения. Купите пакет для продолжения работы!"
        await message.answer(text, parse_mode="HTML", reply_markup=get_buy_package_keyboard())
    elif balance['total'] <= 3:
        text += "\n\n💡 Рекомендуем пополнить баланс заранее!"
        await message.answer(text, parse_mode="HTML", reply_markup=get_low_balance_keyboard())
    else:
        text += "\n\n✅ У вас достаточно изображений для работы!"
        await message.answer(text, parse_mode="HTML")


@router.message(F.text == "💎 Купить пакет")
async def packages_handler(message: Message):
    """Handle packages request"""
    db = get_db()
    async with db.get_session() as session:
        packages = await get_all_packages(session)
        balance = await get_user_balance(session, message.from_user.id)

    packages_list = [
        {
            "id": p.id,
            "name": p.name,
            "images_count": p.images_count,
            "price_rub": float(p.price_rub)
        }
        for p in packages
    ]

    text = (
        "💎 <b>Доступные пакеты:</b>\n\n"
        f"🎁 Бесплатно: 3 изображения (осталось: {balance['free']})\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите пакет для покупки:"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_packages_keyboard(packages_list))


@router.message(F.text == "ℹ️ Информация")
async def info_handler(message: Message):
    """Handle information request"""
    text = (
        "ℹ️ <b>Информация о боте</b>\n\n"
        "Выберите интересующий раздел:"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_info_menu())


@router.callback_query(F.data == "info_how_it_works")
async def info_how_it_works_handler(callback: CallbackQuery):
    """Handle 'How it works' info request"""
    text = (
        "❓ <b>Как это работает?</b>\n\n"
        "📸 <b>Два режима обработки:</b>\n\n"
        "1️⃣ <b>Отправка как Фото (с компрессией)</b>\n"
        "• Отправьте изображение обычным способом\n"
        "• Telegram автоматически сжимает его\n"
        "• Результат: изображение на <b>белом фоне</b>\n"
        "• Быстро, удобно для веб-публикаций\n\n"
        "2️⃣ <b>Отправка как Документ (без компрессии)</b>\n"
        "• Нажмите 📎 (скрепка) → выберите файл\n"
        "• Отправьте как документ\n"
        "• Результат: PNG с <b>прозрачным фоном</b>\n"
        "• Высокое качество для дизайна, печати\n\n"
        "🎯 <b>Процесс обработки:</b>\n"
        "1. Я проанализирую изображение\n"
        "2. Построю оптимальный промпт\n"
        "3. Используя AI, удалю фон\n"
        "4. Вернуть результат\n\n"
        "🔍 <b>Бот автоматически определяет:</b>\n"
        "• Сложные края (волосы, мех)\n"
        "• Прозрачные объекты (стекло)\n"
        "• Движение и размытие\n\n"
        "✨ Выбирайте режим в зависимости от ваших потребностей!"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "info_offer")
async def info_offer_handler(callback: CallbackQuery):
    """Handle offer/agreement info request"""
    text = (
        "📄 <b>Публичная оферта</b>\n\n"
        "Используя данного бота, вы соглашаетесь со следующими условиями:\n\n"
        "1. <b>Услуга</b>\n"
        "Бот предоставляет услугу удаления фона с изображений с использованием AI технологий.\n\n"
        "2. <b>Стоимость</b>\n"
        "• Первые 3 обработки - бесплатно\n"
        "• Далее - согласно выбранному пакету\n\n"
        "3. <b>Оплата</b>\n"
        "Оплата производится через платежную систему Robokassa.\n\n"
        "4. <b>Качество</b>\n"
        "Результат зависит от качества исходного изображения. "
        "Мы не гарантируем идеальный результат для всех изображений.\n\n"
        "5. <b>Использование изображений</b>\n"
        "Ваши изображения обрабатываются через OpenRouter API и не сохраняются на наших серверах после обработки.\n\n"
        "📧 По вопросам: обратитесь в поддержку через бот"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "info_refund")
async def info_refund_handler(callback: CallbackQuery):
    """Handle refund policy info request"""
    text = (
        "💸 <b>Условия возврата</b>\n\n"
        "1. <b>Возврат средств</b>\n"
        "Возврат средств возможен в течение 14 дней с момента покупки, "
        "если услуга не была использована (изображения не были обработаны).\n\n"
        "2. <b>Частичный возврат</b>\n"
        "Если вы использовали часть купленного пакета, возврат производится "
        "за неиспользованные обработки по пропорциональной стоимости.\n\n"
        "3. <b>Процедура возврата</b>\n"
        "Для оформления возврата:\n"
        "• Обратитесь в поддержку через бот\n"
        "• Укажите номер заказа и причину возврата\n"
        "• Средства будут возвращены в течение 5-7 рабочих дней\n\n"
        "4. <b>Отказ в возврате</b>\n"
        "Возврат невозможен, если:\n"
        "• Прошло более 14 дней с покупки\n"
        "• Все изображения из пакета были использованы\n"
        "• Обнаружены признаки злоупотребления услугой\n\n"
        "💬 Для оформления возврата обратитесь в поддержку"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "info_privacy")
async def info_privacy_handler(callback: CallbackQuery):
    """Handle privacy policy info request"""
    text = (
        "🔒 <b>Политика конфиденциальности</b>\n\n"
        "1. <b>Сбор данных</b>\n"
        "Мы собираем:\n"
        "• Telegram ID и username\n"
        "• Историю транзакций\n"
        "• Статистику использования\n\n"
        "2. <b>Обработка изображений</b>\n"
        "• Изображения отправляются в OpenRouter API для обработки\n"
        "• Мы сохраняем только Telegram file_id для истории\n"
        "• Сами изображения не хранятся на наших серверах\n"
        "• OpenRouter не сохраняет ваши изображения после обработки\n\n"
        "3. <b>Использование данных</b>\n"
        "Ваши данные используются исключительно для:\n"
        "• Предоставления услуги\n"
        "• Обработки платежей\n"
        "• Связи с вами по вопросам поддержки\n\n"
        "4. <b>Защита данных</b>\n"
        "• Все данные хранятся в защищенной базе данных\n"
        "• Используется шифрование соединения\n"
        "• Доступ имеют только авторизованные администраторы\n\n"
        "5. <b>Удаление данных</b>\n"
        "Для удаления ваших данных обратитесь в поддержку.\n\n"
        "📧 Вопросы: обратитесь в поддержку через бот"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    """Handle back to menu"""
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data == "contact_support")
async def contact_support_handler(callback: CallbackQuery):
    """Handle contact support button from error messages"""
    text = (
        "💬 <b>Обратная связь</b>\n\n"
        "Выберите тип обращения:"
    )

    from app.keyboards.user_kb import get_support_menu
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_support_menu())
    await callback.answer()


@router.callback_query(F.data == "try_again")
async def try_again_handler(callback: CallbackQuery):
    """Handle try again button"""
    await callback.message.delete()
    await callback.message.answer(
        "📸 <b>Отправьте изображение одним из способов:</b>\n\n"
        "1️⃣ <b>Как Фото</b> → Результат на белом фоне\n"
        "2️⃣ <b>Как Документ</b> (📎) → PNG с прозрачным фоном\n\n"
        "💡 Для лучшего результата используйте качественные фото с хорошим освещением.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "show_packages")
async def show_packages_handler(callback: CallbackQuery):
    """Handle show packages button"""
    db = get_db()
    async with db.get_session() as session:
        packages = await get_all_packages(session)
        balance = await get_user_balance(session, callback.from_user.id)

    packages_list = [
        {
            "id": p.id,
            "name": p.name,
            "images_count": p.images_count,
            "price_rub": float(p.price_rub)
        }
        for p in packages
    ]

    text = (
        "💎 <b>Доступные пакеты:</b>\n\n"
        f"🎁 Бесплатно: 3 изображения (осталось: {balance['free']})\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите пакет для покупки:"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_packages_keyboard(packages_list))
    await callback.answer()


@router.callback_query(F.data == "check_balance")
async def check_balance_handler(callback: CallbackQuery):
    """Handle check balance button"""
    from aiogram.exceptions import TelegramBadRequest

    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, callback.from_user.id)

    text = (
        "📊 <b>Ваш баланс:</b>\n\n"
        f"🎁 Бесплатных изображений: {balance['free']}\n"
        f"💎 Оплаченных изображений: {balance['paid']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📸 Всего доступно: {balance['total']}"
    )

    try:
        if balance['total'] == 0:
            text += "\n\n💰 У вас закончились изображения. Купите пакет для продолжения работы!"
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_buy_package_keyboard())
        elif balance['total'] <= 3:
            text += "\n\n💡 Рекомендуем пополнить баланс заранее!"
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_low_balance_keyboard())
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    except TelegramBadRequest as e:
        # Message content is identical, just answer the callback
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.message(F.photo)
@error_handler
async def process_image_handler(message: Message):
    """Handle image processing"""
    # Check balance
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, message.from_user.id)

        if balance['total'] <= 0:
            await message.answer(
                "❌ У вас закончились изображения!\n\n"
                "💎 Купите пакет для продолжения работы.",
                reply_markup=get_buy_package_keyboard()
            )
            return

        # Show processing message
        status_msg = await message.answer("⏳ Обрабатываю изображение...")

        try:
            # Download photo
            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_bytes = file_bytes.read()

            # Analyze and build prompt
            processor = ImageProcessor()
            analysis = processor.analyze_image(image_bytes)
            prompt = PromptBuilder.build_prompt(analysis)

            # Process image with OpenRouter
            openrouter = OpenRouterService()
            result = await openrouter.remove_background(image_bytes, prompt)

            if result['success']:
                # Send result
                from aiogram.types import BufferedInputFile

                output_file = BufferedInputFile(
                    result['image_bytes'],
                    filename="removed_bg.png"
                )

                # Determine if using free or paid image
                is_free = balance['free'] > 0

                # Decrease balance
                await decrease_balance(session, message.from_user.id)

                # Update stats
                await update_user_stats(session, message.from_user.id)

                # Save to database
                await save_processed_image(
                    session,
                    message.from_user.id,
                    photo.file_id,
                    "processed_file_id",  # Would be the actual file_id after upload
                    prompt,
                    is_free
                )

                # Get new balance
                new_balance = await get_user_balance(session, message.from_user.id)

                caption = f"✅ Готово! Фон успешно удален (на белом фоне).\n\n📊 Осталось изображений: {new_balance['total']}\n\n💡 Для PNG с прозрачным фоном отправьте изображение как документ (📎)"

                # Add contextual message based on balance
                if new_balance['total'] == 0:
                    caption += "\n\n⚠️ Это была ваша последняя обработка!"
                elif new_balance['total'] <= 2:
                    caption += f"\n\n💡 Осталось совсем немного обработок!"

                # Send result with optional keyboard
                if new_balance['total'] == 0:
                    await message.answer_photo(output_file, caption=caption)
                    await message.answer(
                        "💎 Хотите продолжить работу? Купите пакет изображений!",
                        reply_markup=get_buy_package_keyboard()
                    )
                elif new_balance['total'] <= 2:
                    await message.answer_photo(output_file, caption=caption)
                    await message.answer(
                        "💡 Рекомендуем пополнить баланс заранее!",
                        reply_markup=get_low_balance_keyboard()
                    )
                else:
                    await message.answer_photo(output_file, caption=caption)

                await status_msg.delete()
            else:
                await status_msg.edit_text(
                    f"❌ Ошибка обработки: {result['error']}\n\n"
                    "Попробуйте другое фото или обратитесь в поддержку.",
                    reply_markup=get_support_contact_keyboard()
                )

        except Exception as e:
            await status_msg.edit_text(
                "❌ Произошла ошибка при обработке изображения.\n\n"
                "Попробуйте еще раз или обратитесь в поддержку.",
                reply_markup=get_support_contact_keyboard()
            )
            print(f"Error processing image: {str(e)}")


@router.message(F.document)
@error_handler
async def process_document_handler(message: Message):
    """Handle document (lossless) image processing"""
    # Check if document is an image
    if not message.document.mime_type or not message.document.mime_type.startswith('image/'):
        await message.answer("⚠️ Пожалуйста, отправьте файл изображения (PNG, JPG и т.д.)")
        return

    # Check balance
    db = get_db()
    async with db.get_session() as session:
        balance = await get_user_balance(session, message.from_user.id)

        if balance['total'] <= 0:
            await message.answer(
                "❌ У вас закончились изображения!\n\n"
                "💎 Купите пакет для продолжения работы.",
                reply_markup=get_buy_package_keyboard()
            )
            return

        # Show processing message
        status_msg = await message.answer("⏳ Обрабатываю изображение без потери качества...")

        try:
            # Download document
            file = await message.bot.get_file(message.document.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            image_bytes = file_bytes.read()

            # Analyze image for prompt building
            processor = ImageProcessor()
            analysis = processor.analyze_image(image_bytes, detect_subject_color=True)

            # Strategy: Try transparent background first (most reliable)
            # If AI doesn't support it well, we have chroma key as fallback
            prompt = PromptBuilder.build_prompt(analysis, transparent=True)

            # Process image with OpenRouter (requesting transparent background)
            openrouter = OpenRouterService()
            result = await openrouter.remove_background(image_bytes, prompt, transparent=True)

            # Fallback: If transparent didn't work well, try chroma key approach
            # (This can be detected by checking if result has transparency)
            # For now, we trust the transparent approach

            if result['success']:
                # Send result as document (lossless)
                from aiogram.types import BufferedInputFile

                output_file = BufferedInputFile(
                    result['image_bytes'],
                    filename=f"nobg_{message.from_user.id}_{message.document.file_unique_id}.png"
                )

                # Determine if using free or paid image
                is_free = balance['free'] > 0

                # Decrease balance
                await decrease_balance(session, message.from_user.id)

                # Update stats
                await update_user_stats(session, message.from_user.id)

                # Save to database
                await save_processed_image(
                    session,
                    message.from_user.id,
                    message.document.file_id,
                    "processed_file_id",  # Would be the actual file_id after upload
                    prompt,
                    is_free
                )

                # Get new balance
                new_balance = await get_user_balance(session, message.from_user.id)

                caption = f"✅ Готово! Фон успешно удален (PNG с прозрачным фоном).\n\n📊 Осталось изображений: {new_balance['total']}\n\n✨ Высокое качество без потери деталей!"

                # Add contextual message based on balance
                if new_balance['total'] == 0:
                    caption += "\n\n⚠️ Это была ваша последняя обработка!"
                elif new_balance['total'] <= 2:
                    caption += f"\n\n💡 Осталось совсем немного обработок!"

                # Send result as document with optional keyboard
                if new_balance['total'] == 0:
                    await message.answer_document(output_file, caption=caption)
                    await message.answer(
                        "💎 Хотите продолжить работу? Купите пакет изображений!",
                        reply_markup=get_buy_package_keyboard()
                    )
                elif new_balance['total'] <= 2:
                    await message.answer_document(output_file, caption=caption)
                    await message.answer(
                        "💡 Рекомендуем пополнить баланс заранее!",
                        reply_markup=get_low_balance_keyboard()
                    )
                else:
                    await message.answer_document(output_file, caption=caption)

                await status_msg.delete()
            else:
                await status_msg.edit_text(
                    f"❌ Ошибка обработки: {result['error']}\n\n"
                    "Попробуйте другое фото или обратитесь в поддержку.",
                    reply_markup=get_support_contact_keyboard()
                )

        except Exception as e:
            await status_msg.edit_text(
                "❌ Произошла ошибка при обработке изображения.\n\n"
                "Попробуйте еще раз или обратитесь в поддержку.",
                reply_markup=get_support_contact_keyboard()
            )
            print(f"Error processing document: {str(e)}")


@router.message(F.text == "📸 Обработать изображение")
async def process_image_request_handler(message: Message):
    """Handle image processing request"""
    await message.answer(
        "📸 <b>Отправьте изображение одним из способов:</b>\n\n"
        "1️⃣ <b>Как Фото</b> (обычная отправка)\n"
        "   ➜ Результат: на <b>белом фоне</b>\n"
        "   ➜ Для быстрого использования\n\n"
        "2️⃣ <b>Как Документ</b> (📎 скрепка → файл)\n"
        "   ➜ Результат: PNG с <b>прозрачным фоном</b>\n"
        "   ➜ Без потери качества\n\n"
        "💡 <b>Советы для лучшего результата:</b>\n"
        "• Используйте фото с хорошим освещением\n"
        "• Четкие границы объекта\n"
        "• Контрастный фон\n\n"
        "✨ Отправляйте изображение!",
        parse_mode="HTML"
    )
