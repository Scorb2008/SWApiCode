import html
import os
import random
import string
import tempfile
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import ContentType

from src.bot.bot import bot
from src.bot.keyboards.inline import (
    admin_main_kb,
    admin_panel_kb,
    broadcast_confirm_kb,
    cancel_kb,
    clear_accounts_confirm_kb,
    promo_type_kb,
    promos_pagination_kb,
    sizes_list_kb,
    user_card_kb,
    users_pagination_kb,
)
from src.bot.states import AdminStates, BroadcastStates
from src.config import settings
from src.db.database import async_session
from src.db.repository import (
    clear_all_accounts,
    create_promo,
    delete_promo,
    get_accounts_count_by_size_and_status,
    get_accounts_count_by_status,
    get_active_promos_count,
    get_promos_count,
    get_promos_paginated,
    get_purchases_by_user,
    get_revenue_by_payment_method,
    get_revenue_last_days,
    get_sizes_list,
    get_sold_accounts_for_export,
    get_total_accounts_count,
    get_total_revenue,
    get_user_by_telegram_id,
    get_users_count,
    get_users_paginated,
    search_users,
    set_ban_status,
    update_balance,
    update_price_by_size,
)
from src.services.excel_parser import parse_excel
from src.services.settings import get_setting, set_setting
from src.services.yookassa import check_yookassa_connection

router = Router()

USERS_PER_PAGE = 10
PROMOS_PER_PAGE = 10

async def _safe_edit(callback: types.CallbackQuery, **kwargs):
    try:
        await callback.message.edit_text(**kwargs)
    except TelegramBadRequest:
        await callback.message.answer(**kwargs)


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids_list


async def _notify_admins(text: str):
    for uid in settings.admin_ids_list:
        try:
            await bot.send_message(uid, text)
        except Exception:
            pass


@router.callback_query(F.data == "admin:clear_accounts:confirm")
async def handle_clear_accounts(callback: types.CallbackQuery):
    async with async_session() as session:
        deleted = await clear_all_accounts(session)
    await _safe_edit(callback, text=
        f"✅ <b>База данных очищена!</b>\nУдалено аккаунтов: <b>{deleted}</b>",
        reply_markup=admin_panel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:"))
async def admin_menu_router(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not _is_admin(user_id):
        await callback.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    action = callback.data.split(":")
    cmd = action[1] if len(action) > 1 else ""

    if cmd == "panel":
        await callback.message.answer(
            "⚙️ <b>Админ панель</b>",
            reply_markup=admin_panel_kb(),
        )

    elif cmd == "dashboard":
        await _show_dashboard(callback)

    elif cmd == "revenue":
        await _show_revenue(callback)

    elif cmd == "upload":
        await state.set_state(AdminStates.waiting_for_excel)
        await callback.message.answer(
            "📥 <b>Загрузка Excel</b>\n\nПришлите .xlsx файл с аккаунтами.\n"
            "Колонки: A-логин, B-пароль, C-размер, D-цена, E-статус",
            reply_markup=cancel_kb,
        )

    elif cmd == "welcome_photo":
        await state.set_state(AdminStates.waiting_for_welcome_photo)
        current = get_setting("welcome_photo")
        text = "📸 <b>Приветственное фото</b>\n\n"
        if current:
            text += f"Текущее фото: <code>{current[:40]}...</code>\n"
        text += "Отправьте новое фото или нажмите ❌ Отмена.\n\n"
        text += "Кнопка «Удалить» — убрать фото."
        await callback.message.answer(
            text,
            reply_markup=_welcome_photo_kb(has_photo=bool(current)),
        )

    elif cmd == "delete_welcome_photo":
        set_setting("welcome_photo", "")
        await callback.message.answer(
            "✅ Приветственное фото удалено.",
            reply_markup=admin_panel_kb(),
        )

    elif cmd == "broadcast":
        await state.set_state(BroadcastStates.entering_text)
        await callback.message.answer(
            "📢 <b>Рассылка</b>\n\nВведите текст для отправки всем пользователям:",
            reply_markup=cancel_kb,
        )

    elif cmd == "search":
        await state.set_state(AdminStates.waiting_for_user_id)
        await callback.message.answer(
            "🔍 <b>Поиск пользователя</b>\n\n"
            "Введите Telegram ID или username (можно с @):",
            reply_markup=cancel_kb,
        )

    elif cmd == "create_promo":
        await state.set_state(AdminStates.creating_promo_type)
        await callback.message.answer(
            "🏷 <b>Создание промокода</b>\n\nВыберите тип:",
            reply_markup=promo_type_kb(),
        )

    elif cmd == "user_info" and len(action) > 2:
        await _show_user_card(callback, int(action[2]))

    elif cmd.startswith("users"):
        page = int(action[2]) if len(action) > 2 else 0
        await _show_users_page(callback, page)

    elif cmd.startswith("promos"):
        page = int(action[2]) if len(action) > 2 else 0
        await _show_promos_page(callback, page, state)

    elif cmd == "delete_promo" and len(action) > 2:
        await _delete_promo(callback, int(action[2]), state)

    elif cmd == "ban" and len(action) > 2:
        await _toggle_ban(callback, int(action[2]), banned=True)

    elif cmd == "unban" and len(action) > 2:
        await _toggle_ban(callback, int(action[2]), banned=False)

    elif cmd == "add_balance" and len(action) > 2:
        await state.update_data(target_tg_id=int(action[2]), balance_mode="add")
        await state.set_state(AdminStates.waiting_for_balance_amount)
        await callback.message.answer(
            "💰 <b>Пополнение баланса</b>\n\nВведите сумму для начисления:",
            reply_markup=cancel_kb,
        )

    elif cmd == "sub_balance" and len(action) > 2:
        await state.update_data(target_tg_id=int(action[2]), balance_mode="sub")
        await state.set_state(AdminStates.waiting_for_balance_amount)
        await callback.message.answer(
            "💰 <b>Списание баланса</b>\n\nВведите сумму для списания:",
            reply_markup=cancel_kb,
        )

    elif cmd == "purchases" and len(action) > 2:
        await _show_user_purchases(callback, int(action[2]))

    elif cmd == "clear_accounts":
        await _confirm_clear_accounts(callback)

    elif cmd == "check_yookassa":
        await _check_yookassa(callback)

    elif cmd == "export":
        await _export_sold_accounts(callback)

    elif cmd == "edit_prices":
        await _show_price_edit(callback)

    elif cmd == "edit_price" and len(action) > 2:
        size = action[2]
        await state.update_data(editing_size=size)
        await state.set_state(AdminStates.waiting_for_new_price)
        await callback.message.answer(
            f"💰 <b>Изменение цены</b>\n\nТариф: {size}\n\nВведите новую цену (в рублях):",
            reply_markup=cancel_kb,
        )

    await callback.answer()


async def _confirm_clear_accounts(callback: types.CallbackQuery):
    async with async_session() as session:
        total = await get_total_accounts_count(session)
    await _safe_edit(callback, text=
        f"⚠️ <b>Очистка базы данных</b>\n\n"
        f"Будут удалены все аккаунты (<b>{total} шт.</b>).\n"
        f"Пользователи, покупки и промокоды останутся.\n\n"
        "Вы уверены?",
        reply_markup=clear_accounts_confirm_kb(),
    )


async def _export_sold_accounts(callback: types.CallbackQuery):
    from tempfile import NamedTemporaryFile
    from openpyxl import Workbook

    async with async_session() as session:
        accounts = await get_sold_accounts_for_export(session)

    if not accounts:
        await _safe_edit(callback, text=
            "📭 Нет проданных аккаунтов.",
            reply_markup=admin_panel_kb(),
        )
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Sold Accounts"
    ws.append(["Login", "Password", "Size", "Price", "Sold To (TG ID)", "Sold At"])

    for a in accounts:
        ws.append([a.login, a.password, a.size, float(a.price), a.sold_to_user_id or "", str(a.sold_at or "")])

    with NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        wb.save(tmp.name)
        file_path = tmp.name

    try:
        await callback.message.answer_document(
            types.input_file.FSInputFile(file_path, filename="sold_accounts.xlsx"),
            caption=f"📥 Экспорт: <b>{len(accounts)}</b> проданных аккаунтов",
            reply_markup=admin_panel_kb(),
        )
    finally:
        os.unlink(file_path)

    await _safe_edit(callback, text="📥 Экспорт готов. Файл отправлен ниже.")
    await callback.answer()


async def _show_price_edit(callback: types.CallbackQuery):
    async with async_session() as session:
        sizes = await get_sizes_list(session)

    if not sizes:
        await _safe_edit(callback, text=
            "📭 Нет тарифов для редактирования.",
            reply_markup=admin_panel_kb(),
        )
        return

    await _safe_edit(callback, text=
        "💰 <b>Редактирование цен</b>\n\nВыберите тариф:",
        reply_markup=sizes_list_kb(sizes),
    )


@router.message(AdminStates.waiting_for_new_price, F.text)
async def handle_new_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    size = data.get("editing_size")

    try:
        new_price = Decimal(message.text)
        if new_price <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Введите положительное число.", reply_markup=cancel_kb)
        return

    async with async_session() as session:
        updated = await update_price_by_size(session, size, new_price)

    await state.clear()
    await message.answer(
        f"✅ <b>Цена обновлена!</b>\n\n"
        f"💎 Тариф: {size}\n"
        f"💰 Новая цена: {new_price:.2f} ₽\n"
        f"📦 Обновлено аккаунтов: <b>{updated}</b>",
        reply_markup=admin_panel_kb(),
    )


async def _check_yookassa(callback: types.CallbackQuery):
    await _safe_edit(callback, text="🔄 Проверка ЮKassa...")
    result = await check_yookassa_connection()

    shop_id = result.get("shop_id", "—")
    lines = [
        "🔍 <b>Проверка ЮKassa</b>\n",
        f"🆔 Shop ID: <code>{shop_id}</code>",
    ]

    if result.get("ok"):
        lines.append("✅ <b>Статус:</b> 🟢 Подключение работает")
        lines.append("")
        lines.append("📌 <b>Проверьте также:</b>")
        lines.append("• Webhook URL в настройках ЮKassa")
        lines.append("  → <code>/yookassa/webhook</code>")
        lines.append("• IP-белый список (если включён)")
        lines.append("• Баланс магазина")
    else:
        error = result.get("error", "Неизвестная ошибка")
        lines.append("❌ <b>Статус:</b> 🔴 Ошибка подключения")
        lines.append(f"⚠️ <code>{html.escape(error[:300])}</code>")
        lines.append("")
        lines.append("💡 <b>Проверьте:</b>")
        lines.append("• <code>YOOKASSA_SHOP_ID</code> в .env")
        lines.append("• <code>YOOKASSA_SECRET_KEY</code> в .env")
        lines.append("• Доступ к api.yookassa.ru с сервера")

    await _safe_edit(callback, text=
        "\n".join(lines),
        reply_markup=admin_panel_kb(),
    )


def _welcome_photo_kb(has_photo: bool) -> types.InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    if has_photo:
        rows.insert(0, [InlineKeyboardButton(text="🗑 Удалить фото", callback_data="admin:delete_welcome_photo")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(AdminStates.waiting_for_welcome_photo, F.content_type == ContentType.PHOTO)
async def handle_welcome_photo(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    set_setting("welcome_photo", file_id)
    await state.clear()
    await message.answer(
        "✅ Приветственное фото установлено!",
        reply_markup=admin_panel_kb(),
    )


@router.message(AdminStates.waiting_for_welcome_photo)
async def handle_welcome_photo_invalid(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Пожалуйста, отправьте фото.", reply_markup=cancel_kb)


@router.message(BroadcastStates.entering_text)
async def broadcast_enter_text(message: types.Message, state: FSMContext):
    text = message.text or message.caption or ""
    has_photo = bool(message.photo)
    photo = message.photo[-1].file_id if has_photo else None

    await state.update_data(broadcast_text=text, broadcast_photo=photo)

    async with async_session() as session:
        total = await get_users_count(session)

    preview = text[:200] + ("..." if len(text) > 200 else "")
    await message.answer(
        f"📢 <b>Предпросмотр рассылки</b>\n\n{preview}\n\n"
        f"👥 Получат: <b>{total}</b> пользователей\n\n"
        "Отправить?",
        reply_markup=broadcast_confirm_kb(),
    )
    await state.set_state(BroadcastStates.confirming)


@router.callback_query(F.data == "broadcast:send", BroadcastStates.confirming)
async def broadcast_send(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    photo = data.get("broadcast_photo")

    await _safe_edit(callback, text="📢 Рассылка запущена...")
    await callback.answer()

    async with async_session() as session:
        from src.db.repository import get_all_users
        users = await get_all_users(session)

    sent = 0
    failed = 0
    for u in users:
        try:
            if photo:
                await bot.send_photo(u.telegram_id, photo=photo, caption=text)
            else:
                await bot.send_message(u.telegram_id, text)
            sent += 1
        except Exception:
            failed += 1

    await state.clear()
    await _safe_edit(callback, text=
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=admin_panel_kb(),
    )


async def _show_dashboard(callback: types.CallbackQuery):
    async with async_session() as session:
        total_users = await get_users_count(session)
        total_accounts = await get_total_accounts_count(session)
        available = await get_accounts_count_by_status(session, "available")
        sold = await get_accounts_count_by_status(session, "sold")
        revenue = await get_total_revenue(session)
        active_promos = await get_active_promos_count(session)
        sizes = await get_sizes_list(session)

        size_lines = []
        for size in sizes:
            avail = await get_accounts_count_by_size_and_status(session, size, "available")
            sld = await get_accounts_count_by_size_and_status(session, size, "sold")
            total_s = avail + sld
            pct = (sld / max(total_s, 1)) * 100
            bar_len = 10
            green = int(avail / max(total_s, 1) * bar_len)
            bar = "🟩" * green + "🟥" * (bar_len - green)
            size_lines.append(f"   {size}: {bar} {avail}🟢 / {sld}🔴 ({pct:.0f}%)")

    lines = [
        "📊 <b>Дашборд</b>\n",
        f"👥 Пользователей: <b>{total_users}</b>",
        f"📦 Всего аккаунтов: <b>{total_accounts}</b>",
        f"   🟢 Свободно: <b>{available}</b>  🔴 Продано: <b>{sold}</b>",
        f"💰 Общая выручка: <b>{revenue:.2f} ₽</b>",
        f"🏷 Активных промокодов: <b>{active_promos}</b>",
    ]
    if size_lines:
        lines.append("\n📊 <b>По размерам:</b>")
        lines.extend(size_lines)

    await _safe_edit(callback, text="\n".join(lines), reply_markup=admin_panel_kb())


async def _show_revenue(callback: types.CallbackQuery):
    async with async_session() as session:
        total = await get_total_revenue(session)
        by_method = await get_revenue_by_payment_method(session)
        last_7 = await get_revenue_last_days(session, 7)
        last_30 = await get_revenue_last_days(session, 30)

    lines = [
        "💰 <b>Выручка</b>\n",
        f"📈 Общая: <b>{total:.2f} ₽</b>\n",
        "🏦 <b>По способам оплаты:</b>",
    ]
    for method, amount in by_method:
        label = {"balance": "💳 Баланс", "yookassa": "💳 ЮKassa",
                  "yookassa_topup": "💳 ЮKassa (пополнение)"}.get(method, method)
        lines.append(f"   {label}: <b>{amount:.2f} ₽</b>")

    lines.extend([
        "",
        f"📊 За 7 дней: <b>{last_7:.2f} ₽</b>",
        f"📊 За 30 дней: <b>{last_30:.2f} ₽</b>",
    ])

    await _safe_edit(callback, text="\n".join(lines), reply_markup=admin_panel_kb())


async def _show_user_card(callback: types.CallbackQuery, target_tg_id: int):
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, target_tg_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        purchases = await get_purchases_by_user(session, user.id)

    text = (
        f"👤 <b>Пользователь</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📛 Имя: {html.escape(user.full_name or '—')}\n"
        f"🌐 Username: @{user.username or '—'}\n"
        f"📅 Регистрация: {user.registered_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"💰 Баланс: <b>{user.balance:.2f} ₽</b>\n"
        f"📦 Покупок: {len(purchases)}\n"
        f"⛔ Статус: {'🔴 Забанен' if user.is_banned else '🟢 Активен'}"
    )
    await _safe_edit(callback, text=
        text,
        reply_markup=user_card_kb(target_tg_id, user.is_banned, back_callback="admin:users:0"),
    )


async def _show_users_page(callback: types.CallbackQuery, page: int):
    async with async_session() as session:
        total = await get_users_count(session)
        total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
        users = await get_users_paginated(session, page * USERS_PER_PAGE, USERS_PER_PAGE)

    if not users:
        await _safe_edit(callback, text="📭 Нет пользователей.", reply_markup=admin_panel_kb())
        return

    await _safe_edit(callback, text=
        f"👥 <b>Пользователи</b> (стр. {page + 1}/{total_pages}) — нажмите на юзера:",
        reply_markup=users_pagination_kb(users, page, total_pages),
    )


async def _show_promos_page(callback: types.CallbackQuery, page: int, state: FSMContext | None = None):
    async with async_session() as session:
        total = await get_promos_count(session)
        total_pages = max(1, (total + PROMOS_PER_PAGE - 1) // PROMOS_PER_PAGE)
        promos = await get_promos_paginated(session, page * PROMOS_PER_PAGE, PROMOS_PER_PAGE)

    if not promos:
        if state:
            await state.set_state(AdminStates.creating_promo_type)
        await _safe_edit(callback, text=
            "📭 Нет промокодов.\n\nСоздайте новый:",
            reply_markup=promo_type_kb(),
        )
        return

    await _safe_edit(callback, text=
        f"🏷 <b>Промокоды</b> (стр. {page + 1}/{total_pages}):\n"
        "🟢 активен | 🔴 израсходован\n\nНажмите 🗑 чтобы удалить.",
        reply_markup=promos_pagination_kb(promos, page, total_pages),
    )


async def _delete_promo(callback: types.CallbackQuery, promo_id: int, state: FSMContext | None = None):
    async with async_session() as session:
        ok = await delete_promo(session, promo_id)
    await callback.answer(
        "✅ Промокод удалён." if ok else "❌ Промокод не найден.",
        show_alert=True,
    )
    await _show_promos_page(callback, 0, state)


async def _toggle_ban(callback: types.CallbackQuery, target_tg_id: int, banned: bool):
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, target_tg_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        await set_ban_status(session, user.id, banned)

    action = "забанен" if banned else "разбанен"
    await callback.answer(f"✅ Пользователь {target_tg_id} {action}.", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=user_card_kb(target_tg_id, banned)
    )


async def _show_user_purchases(callback: types.CallbackQuery, target_tg_id: int):
    async with async_session() as session:
        user = await get_user_by_telegram_id(session, target_tg_id)
        if not user:
            await callback.answer("❌ Пользователь не найден.", show_alert=True)
            return
        purchases = await get_purchases_by_user(session, user.id)

    back = f"admin:user_info:{target_tg_id}"
    if not purchases:
        await _safe_edit(callback, text=
            f"📭 У пользователя <code>{target_tg_id}</code> нет покупок.",
            reply_markup=user_card_kb(target_tg_id, user.is_banned, back_callback=back),
        )
        return

    lines = [f"📜 <b>История покупок</b> <code>{target_tg_id}</code>:\n"]
    for p in purchases[:10]:
        acc_login = html.escape(p.account.login) if p.account else "—"
        lines.append(
            f"🕐 {p.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"💵 {p.amount:.2f} ₽ | 🔑 <code>{acc_login}</code>\n"
            f"💳 {p.payment_method}\n" + "─" * 15
        )
    if len(purchases) > 10:
        lines.append(f"... и ещё {len(purchases) - 10}")

    await _safe_edit(callback, text=
        "\n".join(lines),
        reply_markup=user_card_kb(target_tg_id, user.is_banned, back_callback=back),
    )


@router.message(AdminStates.waiting_for_excel, F.content_type == ContentType.DOCUMENT)
async def handle_excel(message: types.Message, state: FSMContext):
    doc = message.document
    if not doc.file_name or not doc.file_name.endswith(".xlsx"):
        await message.answer("❌ Пожалуйста, отправьте файл в формате .xlsx")
        return

    tg_file = await message.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file_path = tmp.name
        await message.bot.download_file(tg_file.file_path, destination=file_path)

    try:
        accounts = parse_excel(file_path)
    except Exception:
        await message.answer("❌ Ошибка парсинга файла. Проверьте формат .xlsx.")
        return
    finally:
        os.unlink(file_path)

    async with async_session() as session:
        added, skipped = await _bulk_insert(session, accounts)

    await state.clear()
    await message.answer(
        f"✅ <b>Загрузка завершена!</b>\n📥 Добавлено: <b>{added}</b>\n⏭ Пропущено (дубликаты): <b>{skipped}</b>",
        reply_markup=admin_panel_kb(),
    )


async def _bulk_insert(session, accounts: list[dict]):
    from src.db.repository import bulk_insert_accounts
    return await bulk_insert_accounts(session, accounts)


@router.message(AdminStates.waiting_for_user_id, F.text)
async def search_user_handler(message: types.Message, state: FSMContext):
    query = message.text.strip()
    async with async_session() as session:
        users = await search_users(session, query)

    if not users:
        await message.answer(
            "❌ Пользователь не найден. Попробуйте другой ID или username.",
            reply_markup=cancel_kb,
        )
        return

    if len(users) == 1:
        u = users[0]
        await state.clear()
        text = (
            f"👤 <b>Пользователь найден</b>\n\n"
            f"🆔 ID: <code>{u.telegram_id}</code>\n"
            f"📛 Имя: {html.escape(u.full_name or '—')}\n"
            f"🌐 Username: @{u.username or '—'}\n"
            f"📅 Регистрация: {u.registered_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"💰 Баланс: <b>{u.balance:.2f} ₽</b>\n"
            f"⛔ Забанен: {'Да' if u.is_banned else 'Нет'}"
        )
        await message.answer(text, reply_markup=user_card_kb(u.telegram_id, u.is_banned))
    else:
        lines = [f"🔍 <b>Найдено {len(users)} пользователей:</b>\n"]
        for u in users[:10]:
            status_icon = "🔴" if u.is_banned else "🟢"
            uname = f"@{u.username}" if u.username else "—"
            lines.append(f"{status_icon} <code>{u.telegram_id}</code> | {uname} | {u.balance:.0f} ₽")
        await message.answer("\n".join(lines), reply_markup=admin_panel_kb())

    await state.clear()


@router.message(AdminStates.waiting_for_balance_amount)
async def balance_amount_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_tg_id = data.get("target_tg_id")
    mode = data.get("balance_mode")

    try:
        amount = Decimal(message.text)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Введите положительное число.", reply_markup=cancel_kb)
        return

    async with async_session() as session:
        user = await get_user_by_telegram_id(session, target_tg_id)
        if not user:
            await message.answer("❌ Пользователь не найден.", reply_markup=admin_panel_kb())
            await state.clear()
            return

        if mode == "add":
            await update_balance(session, user.id, amount)
            action_text = f"➕ Начислено <b>{amount:.2f} ₽</b>"
        else:
            await update_balance(session, user.id, -amount)
            action_text = f"➖ Списано <b>{amount:.2f} ₽</b>"
        await session.refresh(user)

    await state.clear()
    await message.answer(
        f"✅ {action_text}\n👤 Пользователь: <code>{target_tg_id}</code>\n"
        f"💰 Текущий баланс: <b>{user.balance:.2f} ₽</b>",
        reply_markup=user_card_kb(target_tg_id, user.is_banned),
    )


@router.callback_query(F.data.startswith("promo_type:"), AdminStates.creating_promo_type)
async def promo_type_chosen(callback: types.CallbackQuery, state: FSMContext):
    promo_type = callback.data.split(":", 1)[1]
    await state.update_data(promo_type=promo_type)
    await state.set_state(AdminStates.creating_promo_value)

    hint = {
        "balance": "Введите сумму пополнения (например: 500)",
        "token": "Введите текст токена для выдачи",
    }.get(promo_type, "Введите значение:")

    await _safe_edit(callback, text=f"🏷 <b>Создание промокода</b>\n\n{hint}:", reply_markup=cancel_kb)
    await callback.answer()


@router.message(AdminStates.creating_promo_value, F.text)
async def promo_value_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    promo_type = data.get("promo_type")

    if promo_type == "balance":
        try:
            value = Decimal(message.text)
            if value <= 0:
                raise ValueError
        except (ValueError, TypeError):
            await message.answer("❌ Введите положительное число.", reply_markup=cancel_kb)
            return
    else:
        value = message.text.strip()
        if not value:
            await message.answer("❌ Введите значение.", reply_markup=cancel_kb)
            return

    await state.update_data(promo_value=str(value))
    await state.set_state(AdminStates.creating_promo_uses)
    await message.answer("Введите количество использований (по умолчанию 1):", reply_markup=cancel_kb)


@router.message(AdminStates.creating_promo_uses, F.text)
async def promo_uses_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    promo_type = data.get("promo_type")
    promo_value = data.get("promo_value")

    try:
        max_uses = int(message.text)
        if max_uses <= 0:
            raise ValueError
    except (ValueError, TypeError):
        max_uses = 1

    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    async with async_session() as session:
        token = promo_value if promo_type == "token" else None
        promo = await create_promo(
            session, code=code, promo_type=promo_type,
            value=Decimal(promo_value) if promo_type == "balance" else Decimal("0"),
            max_uses=max_uses, token_value=token,
        )

    display_value = promo_value if promo_type == "token" else f"{promo_value} ₽"
    await state.clear()
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n🎟 Код: <code>{promo.code}</code>\n"
        f"🏷 Тип: {promo.promo_type}\n📦 Значение: {display_value}\n🔄 Использований: {max_uses}",
        reply_markup=admin_panel_kb(),
    )
