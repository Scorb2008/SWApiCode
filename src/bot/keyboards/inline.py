from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def user_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить токен", callback_data="menu:buy")],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
            InlineKeyboardButton(text="📜 История", callback_data="menu:history"),
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить", callback_data="menu:topup"),
            InlineKeyboardButton(text="🎟 Промокод", callback_data="menu:promo"),
        ],
    ])


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить токен", callback_data="menu:buy")],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
            InlineKeyboardButton(text="📜 История", callback_data="menu:history"),
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить", callback_data="menu:topup"),
            InlineKeyboardButton(text="🎟 Промокод", callback_data="menu:promo"),
        ],
        [InlineKeyboardButton(text="⚙️ Админ панель", callback_data="admin:panel")],
    ])


def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Дашборд", callback_data="admin:dashboard"),
            InlineKeyboardButton(text="📥 Excel", callback_data="admin:upload"),
        ],
        [
            InlineKeyboardButton(text="📸 Фото", callback_data="admin:welcome_photo"),
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton(text="💰 Выручка", callback_data="admin:revenue"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data="admin:search"),
        ],
        [
            InlineKeyboardButton(text="👥 Юзеры", callback_data="admin:users:0"),
            InlineKeyboardButton(text="🏷 Промокоды", callback_data="admin:promos:0"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])


cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
])


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast:send"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
        ],
    ])


def size_selection_kb(sizes: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for size, count in sizes:
        builder.button(
            text=f"💎 {size}  —  {count} шт. в наличии",
            callback_data=f"size:{size}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def payment_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Баланс", callback_data="pay:balance"),
            InlineKeyboardButton(text="💳 ЮKassa", callback_data="pay:yookassa"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def confirm_purchase_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm:yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:no"),
        ],
    ])


def user_card_kb(
    telegram_id: int, is_banned: bool, back_callback: str = "admin:panel"
) -> InlineKeyboardMarkup:
    ban_btn = (
        InlineKeyboardButton(text="🔇 Забанить", callback_data=f"admin:ban:{telegram_id}")
        if not is_banned
        else InlineKeyboardButton(text="🔊 Разбанить", callback_data=f"admin:unban:{telegram_id}")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Пополнить", callback_data=f"admin:add_balance:{telegram_id}"),
            InlineKeyboardButton(text="➖ Списать", callback_data=f"admin:sub_balance:{telegram_id}"),
        ],
        [ban_btn],
        [InlineKeyboardButton(text="📜 История покупок", callback_data=f"admin:purchases:{telegram_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
    ])


def users_pagination_kb(
    users: list, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for u in users:
        status_icon = "🟢" if not u.is_banned else "🔴"
        uname = f"@{u.username}" if u.username else "—"
        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {u.telegram_id} | {uname} | {u.balance:.0f} ₽",
                callback_data=f"admin:user_info:{u.telegram_id}",
            )
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:users:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:users:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ В админ панель", callback_data="admin:panel"))
    return builder.as_markup()


def promos_pagination_kb(promos: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in promos:
        status = "🟢" if p.is_active else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {p.code} | {p.promo_type} | {p.used_count}/{p.max_uses}",
                callback_data="noop",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"admin:delete_promo:{p.id}"),
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:promos:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:promos:{page + 1}"))
    builder.row(*nav)
    builder.row(
        InlineKeyboardButton(text="🏷 Создать промокод", callback_data="admin:create_promo"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:panel"),
    )
    return builder.as_markup()


def promo_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс (пополнение)", callback_data="promo_type:balance")],
        [InlineKeyboardButton(text="🏷 Скидка (процент)", callback_data="promo_type:discount")],
        [InlineKeyboardButton(text="🎟 Токен (выдача)", callback_data="promo_type:token")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
