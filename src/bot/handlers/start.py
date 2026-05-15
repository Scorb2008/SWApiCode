import html
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from src.bot.keyboards.inline import admin_main_kb, user_main_kb
from src.bot.states import BuyStates, TopUpStates
from src.config import settings
from src.db.database import async_session
from src.db.repository import (
    create_purchase,
    delete_pending_payment,
    get_or_create_user,
    get_purchase_by_payment_id,
    reserve_and_sell_accounts,
)
from src.services.settings import get_setting
from src.services.yookassa import get_payment_status

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
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

    state_data = await state.get_data()
    payment_id = state_data.get("payment_id")

    if payment_id:
        try:
            payment_data = await get_payment_status(payment_id)
        except Exception:
            await message.answer(
                "❌ Ошибка проверки платежа. Попробуйте позже.",
                reply_markup=user_main_kb(),
            )
            return

        status = payment_data.get("status")

        if status == "succeeded":
            async with async_session() as session:
                existing = await get_purchase_by_payment_id(session, payment_id)
                if existing:
                    await delete_pending_payment(session, payment_id)
                    await state.clear()
                    await message.answer("✅ Платёж уже обработан.", reply_markup=user_main_kb())
                    return

            current_state = await state.get_state()

            if current_state == TopUpStates.waiting_for_payment.state:
                amount = Decimal(state_data.get("pending_amount", "0"))
                async with async_session() as session:
                    user = await get_or_create_user(session, message.from_user.id)
                    user.balance += amount
                    session.add(await create_purchase(
                        session, user.id, amount, "yookassa_topup", payment_id
                    ))
                    await session.commit()
                    await delete_pending_payment(session, payment_id)
                await state.clear()
                await message.answer(
                    f"✅ <b>Баланс пополнен на {amount:.2f} ₽</b>",
                    reply_markup=user_main_kb(),
                )
                return

            elif current_state == BuyStates.choosing_payment.state:
                total = Decimal(state_data.get("pending_total", "0"))
                quantity = int(state_data.get("quantity", 1))
                size = state_data.get("chosen_size", "")
                async with async_session() as session:
                    user = await get_or_create_user(session, message.from_user.id)
                    try:
                        accounts = await reserve_and_sell_accounts(
                            session, size, quantity, user.id, total
                        )
                        for acc in accounts:
                            purchase = await create_purchase(
                                session, user.id, acc.price, "yookassa", payment_id
                            )
                            purchase.account_id = acc.id
                            session.add(purchase)
                        await session.commit()
                    except ValueError:
                        await create_purchase(
                            session, user.id, total, "yookassa_refund", payment_id
                        )
                        user.balance += total
                        await session.commit()
                        await state.clear()
                        await message.answer(
                            "❌ Аккаунты закончились. Средства возвращены на баланс.",
                            reply_markup=user_main_kb(),
                        )
                        return
                    await delete_pending_payment(session, payment_id)
                await state.clear()
                creds = "\n\n".join(
                    f"🔑 Логин: <code>{html.escape(a.login)}</code>\n🔐 Пароль: <code>{html.escape(a.password)}</code>"
                    for a in accounts
                )
                await message.answer(
                    f"✅ <b>Покупка успешна!</b>\n\n"
                    f"{creds}\n\n"
                    f"💵 Списано: {total:.2f} ₽"
                    f"ℹ️ <b>Сайт для входа: https://codex.sale</b>",
                    reply_markup=user_main_kb(),
                )
                return

        elif status == "canceled":
            async with async_session() as session:
                await delete_pending_payment(session, payment_id)
            await state.clear()
            await message.answer("❌ Платёж отменён.", reply_markup=user_main_kb())
            return

        else:
            await message.answer(
                "⏳ Платёж ещё не подтверждён. Нажмите /start позже.",
                reply_markup=user_main_kb(),
            )
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
    try:
        await callback.message.edit_text("👋 Главное меню:", reply_markup=kb)
    except Exception:
        await callback.message.answer("👋 Главное меню:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    is_admin = user_id in settings.admin_ids_list
    kb = admin_main_kb() if is_admin else user_main_kb()
    try:
        await callback.message.edit_text("❌ Действие отменено.\n\n👋 Главное меню:", reply_markup=kb)
    except Exception:
        await callback.message.answer("❌ Действие отменено.\n\n👋 Главное меню:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()
