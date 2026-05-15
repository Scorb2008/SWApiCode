from decimal import Decimal
import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.keyboards.inline import (
    cancel_kb,
    confirm_purchase_kb,
    payment_method_kb,
    size_selection_kb,
    user_main_kb,
)
from src.bot.states import BuyStates, PromoStates, TopUpStates
from src.db.database import async_session
from src.db.repository import (
    create_purchase,
    get_available_accounts_by_size,
    get_available_count_by_size,
    get_or_create_user,
    get_promo_by_code,
    get_purchase_count_by_user,
    get_purchases_by_user,
    reserve_and_sell_accounts,
    use_promo,
)
from src.services.yookassa import create_yookassa_payment

router = Router()


@router.callback_query(F.data == "menu:buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        if user.is_banned:
            await callback.answer("⛔ Вы забанены.", show_alert=True)
            return

        sizes = await get_available_count_by_size(session)
        if not sizes:
            await callback.answer("😕 Нет доступных аккаунтов.", show_alert=True)
            return

    await state.set_state(BuyStates.choosing_size)
    await state.update_data(sizes=sizes)
    await callback.message.answer(
        "💎 <b>Выберите тариф:</b>",
        reply_markup=size_selection_kb(sizes),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def show_profile(callback: types.CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        purchase_count = await get_purchase_count_by_user(session, user.id)

    await callback.message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📅 Регистрация: {user.registered_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"💰 Баланс: <b>{user.balance:.2f} ₽</b>\n"
        f"📦 Покупок: <b>{purchase_count}</b>",
        reply_markup=user_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:history")
async def show_purchase_history(callback: types.CallbackQuery):
    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        purchases = await get_purchases_by_user(session, user.id)

    if not purchases:
        await callback.message.answer(
            "📭 У вас ещё нет покупок.",
            reply_markup=user_main_kb(),
        )
        await callback.answer()
        return

    lines = []
    for p in purchases[:15]:
        acc_login = html.escape(p.account.login) if p.account else "—"
        lines.append(
            f"🕐 {p.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"💵 Сумма: {p.amount:.2f} ₽\n"
            f"🔑 Логин: <code>{acc_login}</code>\n"
            f"💳 Способ: {p.payment_method}\n"
            + ("─" * 20)
        )

    text = f"📜 <b>История покупок</b> (последние 15):\n\n" + "\n".join(lines)
    if len(purchases) > 15:
        text += f"\n... и ещё {len(purchases) - 15} покупок"

    await callback.message.answer(text, reply_markup=user_main_kb())
    await callback.answer()


@router.callback_query(F.data == "menu:topup")
async def top_up_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(TopUpStates.entering_amount)
    await callback.message.answer(
        "💰 <b>Пополнение баланса</b>\n\n"
        "Введите сумму от <b>40</b> до <b>15000</b> ₽:",
        reply_markup=cancel_kb,
    )
    await callback.answer()


@router.callback_query(F.data == "menu:promo")
async def promo_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.entering_code)
    await callback.message.answer(
        "🎟 <b>Активация промокода</b>\n\nВведите промокод:",
        reply_markup=cancel_kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("size:"), BuyStates.choosing_size)
async def size_chosen(callback: types.CallbackQuery, state: FSMContext):
    size = callback.data.split(":", 1)[1]
    data = await state.get_data()
    sizes: list[tuple[str, int]] = data.get("sizes", [])

    size_info = next(((s, c) for s, c in sizes if s == size), None)
    if not size_info:
        await callback.message.edit_text("😕 Тариф не найден.")
        await callback.answer()
        return

    await state.update_data(chosen_size=size, size_count=size_info[1])
    await state.set_state(BuyStates.choosing_quantity)

    async with async_session() as session:
        accounts = await get_available_accounts_by_size(session, size)
        price = accounts[0].price if accounts else Decimal("0")

    await callback.message.edit_text(
        f"💎 <b>Тариф: {size}</b>\n"
        f"💰 Цена за шт.: <b>{price:.2f} ₽</b>\n"
        f"📦 Доступно: <b>{size_info[1]} шт.</b>\n\n"
        "Введите количество:",
        reply_markup=cancel_kb,
    )
    await callback.answer()


@router.message(BuyStates.choosing_quantity)
async def quantity_chosen(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ Введите положительное число.", reply_markup=cancel_kb)
        return

    quantity = int(message.text)
    data = await state.get_data()
    size_count = data.get("size_count", 0)

    if quantity > size_count:
        await message.answer(
            f"❌ Доступно только {size_count} шт. Введите меньшее количество.",
            reply_markup=cancel_kb,
        )
        return

    await state.update_data(quantity=quantity)

    async with async_session() as session:
        accounts = await get_available_accounts_by_size(session, data["chosen_size"])
        unit_price = accounts[0].price if accounts else Decimal("0")
        total = unit_price * quantity

    await state.update_data(unit_price=str(unit_price), total=str(total))
    await state.set_state(BuyStates.confirming)

    await message.answer(
        f"<b>📋 Проверьте заказ:</b>\n\n"
        f"💎 Тариф: {data['chosen_size']}\n"
        f"🔢 Количество: {quantity} шт.\n"
        f"💰 Цена за шт.: {unit_price:.2f} ₽\n"
        f"💵 Итого: <b>{total:.2f} ₽</b>\n\n"
        "Подтверждаете?",
        reply_markup=confirm_purchase_kb(),
    )


@router.callback_query(F.data == "confirm:yes", BuyStates.confirming)
async def confirm_purchase(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    quantity = data["quantity"]
    size = data["chosen_size"]
    total = Decimal(data["total"])

    await state.set_state(BuyStates.choosing_payment)
    await state.update_data(pending_price=str(total))
    await callback.message.edit_text(
        f"💵 <b>К оплате: {total:.2f} ₽</b>\n\nВыберите способ оплаты:",
        reply_markup=payment_method_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "confirm:no", BuyStates.confirming)
async def cancel_purchase(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Покупка отменена.", reply_markup=user_main_kb())
    await callback.answer()


@router.callback_query(F.data == "pay:balance", BuyStates.choosing_payment)
async def pay_with_balance(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total = Decimal(data["total"])
    quantity = data["quantity"]
    size = data["chosen_size"]

    async with async_session() as session:
        user = await get_or_create_user(session, callback.from_user.id)
        if user.balance < total:
            await callback.message.edit_text(
                f"❌ Недостаточно средств.\n"
                f"💰 Баланс: {user.balance:.2f} ₽\n"
                f"💵 Требуется: {total:.2f} ₽\n\n"
                "Пополните баланс и попробуйте снова.",
                reply_markup=user_main_kb(),
            )
            await callback.answer()
            return

        try:
            accounts = await reserve_and_sell_accounts(session, size, quantity, user.id, total)
            user.balance -= total
            for acc in accounts:
                purchase = await create_purchase(session, user.id, acc.price, "balance")
                purchase.account_id = acc.id
                session.add(purchase)
            await session.commit()
        except ValueError as e:
            await callback.message.edit_text(f"❌ {e}", reply_markup=user_main_kb())
            await callback.answer()
            return

    creds = "\n\n".join(
        f"🔑 <code>{html.escape(a.login)}</code>\n🔐 <code>{html.escape(a.password)}</code>" for a in accounts
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Покупка успешна!</b>\n\n"
        f"{creds}\n\n"
        f"💵 Списано: {total:.2f} ₽",
        reply_markup=user_main_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "pay:yookassa", BuyStates.choosing_payment)
async def pay_with_yookassa(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total = Decimal(data["total"])
    quantity = data["quantity"]
    size = data["chosen_size"]

    try:
        payment_url, payment_id = await create_yookassa_payment(
            amount=float(total),
            description=f"Покупка {quantity}x {size}",
            metadata={
                "telegram_id": str(callback.from_user.id),
                "size": size,
                "quantity": str(quantity),
                "total": str(total),
                "action": "purchase",
            },
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка создания платежа: {e}",
            reply_markup=payment_method_kb(),
        )
        await callback.answer()
        return

    await state.update_data(payment_id=payment_id, pending_total=str(total))
    await callback.message.edit_text(
        "💳 <b>Ссылка для оплаты:</b>\n\n"
        "После оплаты нажмите /start, чтобы проверить статус.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]),
    )
    await callback.answer()


@router.message(TopUpStates.entering_amount)
async def top_up_amount(message: types.Message, state: FSMContext):
    try:
        amount = Decimal(message.text)
        if amount < 40 or amount > 15000:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(
            "❌ Сумма должна быть от 40 до 15000 ₽. Введите число.",
            reply_markup=cancel_kb,
        )
        return

    try:
        payment_url, payment_id = await create_yookassa_payment(
            amount=float(amount),
            description="Пополнение баланса",
            metadata={
                "telegram_id": str(message.from_user.id),
                "amount": str(amount),
                "action": "topup",
            },
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка создания платежа: {e}", reply_markup=cancel_kb)
        return

    await state.clear()
    await message.answer(
        "💳 <b>Ссылка для оплаты:</b>\n\n"
        "После оплаты нажмите /start для проверки баланса.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
        ]),
    )


@router.message(PromoStates.entering_code)
async def promo_apply(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    async with async_session() as session:
        promo = await get_promo_by_code(session, code)
        if not promo:
            await message.answer(
                "❌ Промокод не найден или неактивен.",
                reply_markup=cancel_kb,
            )
            return

        user = await get_or_create_user(session, message.from_user.id)

        if promo.promo_type == "balance":
            user.balance += promo.value
            await use_promo(session, promo)
            await session.commit()
            await message.answer(
                f"✅ <b>Баланс пополнен на {promo.value:.2f} ₽</b>",
                reply_markup=user_main_kb(),
            )
        elif promo.promo_type == "token":
            token_text = html.escape(promo.token_value or str(promo.value))
            await use_promo(session, promo)
            await session.commit()
            await message.answer(
                f"✅ <b>Получен токен:</b>\n<code>{token_text}</code>",
                reply_markup=user_main_kb(),
            )
        elif promo.promo_type == "discount":
            await message.answer(
                f"🎉 <b>Скидка {promo.value}%</b> будет применена при следующей покупке.",
                reply_markup=user_main_kb(),
            )
            await state.update_data(discount=float(promo.value))

    await state.clear()
