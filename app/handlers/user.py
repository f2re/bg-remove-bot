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
    get_main_menu, get_packages_keyboard, get_info_menu, get_back_keyboard
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
        "Я помогу удалить фон с изображений.\n\n"
        f"🎁 Вам доступно {settings.FREE_IMAGES_COUNT} бесплатные обработки!\n\n"
        "Просто отправьте мне фото, и я уберу фон за несколько секунд."
    )

    await message.answer(welcome_text, reply_markup=get_main_menu())


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

    if balance['total'] == 0:
        text += "\n\n💰 У вас закончились изображения. Купите пакет для продолжения работы!"

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
        "1. Отправьте мне изображение\n"
        "2. Я проанализирую его и построю оптимальный промпт\n"
        "3. Используя AI модель, я удалю фон\n"
        "4. Вы получите изображение с прозрачным фоном\n\n"
        "🎯 Бот автоматически определяет:\n"
        "• Сложные края (волосы, мех)\n"
        "• Прозрачные объекты (стекло)\n"
        "• Движение и размытие\n\n"
        "✨ Результат - чистое изображение без фона!"
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(callback: CallbackQuery):
    """Handle back to menu"""
    await callback.message.delete()
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
                reply_markup=get_main_menu()
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

                await message.answer_photo(
                    output_file,
                    caption=f"✅ Готово! Фон успешно удален.\n\n📊 Осталось изображений: {new_balance['total']}"
                )

                await status_msg.delete()
            else:
                await status_msg.edit_text(
                    f"❌ Ошибка обработки: {result['error']}\n\n"
                    "Попробуйте другое фото или обратитесь в поддержку."
                )

        except Exception as e:
            await status_msg.edit_text(
                "❌ Произошла ошибка при обработке изображения.\n\n"
                "Попробуйте еще раз или обратитесь в поддержку."
            )
            print(f"Error processing image: {str(e)}")


@router.message(F.text == "📸 Обработать изображение")
async def process_image_request_handler(message: Message):
    """Handle image processing request"""
    await message.answer(
        "📸 Отправьте мне изображение, с которого нужно удалить фон.\n\n"
        "💡 Для лучшего результата используйте качественные фото с хорошим освещением."
    )
