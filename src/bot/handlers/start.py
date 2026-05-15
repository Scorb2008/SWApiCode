from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from src.bot.keyboards.inline import admin_main_kb, user_main_kb
from src.config import settings
from src.db.database import async_session
from src.db.repository import get_or_create_user
from src.services.settings import get_setting

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    async with async_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        is_admin = message.from_user.id in settings.admin_ids_list
        if is_admin and not user.is_admin:
            user.is_admin = True
            await session.commit()

    if user.is_banned:
        await message.answer("⛔ Вы забанены. Обратитесь к администратору.")
        return

    kb = admin_main_kb() if user.is_admin else user_main_kb()
    text = (
        f"👋 Добро пожаловать, {message.from_user.full_name}!\n\n"
        "Здесь вы можете приобрести аккаунты Codex API.\n"
        "Используйте кнопки ниже для навигации."
    )
    photo = get_setting("welcome_photo")
    if photo:
        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    is_admin = user_id in settings.admin_ids_list
    kb = admin_main_kb() if is_admin else user_main_kb()
    await callback.message.edit_text(
        "👋 Главное меню:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    is_admin = user_id in settings.admin_ids_list
    kb = admin_main_kb() if is_admin else user_main_kb()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\n👋 Главное меню:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()
