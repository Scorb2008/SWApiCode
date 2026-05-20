import asyncio
import json
import logging
import random
import string
from datetime import datetime
from decimal import Decimal

from src.config import settings
from src.db.database import async_session
from src.db.models import PromoCode
from src.db.repository import get_available_accounts_by_size, get_sizes_list

logger = logging.getLogger(__name__)

FUNPAY_ENABLED = False


async def start_funpay_listener():
    global FUNPAY_ENABLED
    if not settings.funpay_golden_key:
        logger.info("FunPay: not configured (FUNPAY_GOLDEN_KEY missing)")
        return
    FUNPAY_ENABLED = True
    asyncio.create_task(_run_listener())


async def _run_listener():
    from FunPayAPI import Account, Runner, enums

    try:
        acc = Account(settings.funpay_golden_key).get()
        logger.info("FunPay: connected as %s (ID: %s)", acc.username, acc.id)
    except Exception as e:
        logger.error("FunPay: failed to connect: %s", e)
        return

    runner = Runner(acc)

    for event in runner.listen(requests_delay=6):
        try:
            if event.type is enums.EventTypes.NEW_ORDER:
                await _handle_new_order(acc, event.order)
        except Exception as e:
            logger.error("FunPay: error processing event: %s", e)


async def _handle_new_order(acc, order):
    description = order.description or ""
    price = order.price
    buyer_username = order.buyer_username
    logger.info(
        "FunPay: new order #%s — %s (%.2f ₽) by @%s",
        order.id, description, price, buyer_username,
    )

    async with async_session() as session:
        size = await _resolve_size(session, description)
        if not size:
            sizes = await get_sizes_list(session)
            msg = (
                f"❌ FunPay заказ #{order.id}: не удалось определить тариф.\n"
                f"Описание: {description}\n"
                f"Покупатель: @{buyer_username}\n"
                f"Сумма: {price:.2f} ₽\n\n"
                f"Доступные размеры в БД: {', '.join(sizes) or '—'}\n"
                f"Проверьте FUNPAY_LOT_MAPPING в .env"
            )
            logger.warning("FunPay: %s", msg)
            await _notify_admins(msg)
            chat = _get_chat(acc, buyer_username)
            if chat:
                acc.send_message(
                    chat.id,
                    "Не удалось определить тариф. Свяжитесь с поддержкой, "
                    "приложив номер заказа.",
                )
            return

        available = await get_available_accounts_by_size(session, size)
        if not available:
            msg = f"❌ FunPay заказ #{order.id}: нет аккаунтов {size}"
            logger.warning("FunPay: %s", msg)
            await _notify_admins(msg)
            chat = _get_chat(acc, buyer_username)
            if chat:
                acc.send_message(
                    chat.id,
                    "К сожалению, аккаунты этого тарифа закончились. "
                    "Свяжитесь с поддержкой для решения вопроса.",
                )
            return

        account = available[0]
        account.status = "sold"
        account.sold_at = datetime.now()

        code = _generate_code()
        promo = PromoCode(
            code=code,
            promo_type="token",
            value=Decimal("0"),
            token_value=f"{account.login}:{account.password}",
            max_uses=1,
            is_active=True,
        )
        session.add(promo)
        await session.commit()

    chat = _get_chat(acc, buyer_username)
    if chat:
        acc.send_message(
            chat.id,
            f"✅ Оплата подтверждена!\n\n"
            f"Ваш промокод: {code}\n\n"
            f"Перейдите в бота и введите этот код, чтобы получить доступ.",
        )

    await _notify_admins(
        f"💰 <b>Продажа через FunPay</b>\n\n"
        f"👤 Покупатель: @{buyer_username}\n"
        f"💎 Тариф: {size}\n"
        f"💵 Сумма: {price:.2f} ₽\n"
        f"🎟 Промокод: <code>{code}</code>\n"
        f"📦 Заказ: #{order.id}"
    )
    logger.info(
        "FunPay: fulfilled order #%s — promo %s for %s",
        order.id, code, buyer_username,
    )


async def _resolve_size(session, description: str) -> str | None:
    db_sizes = await get_sizes_list(session)
    desc_lower = description.lower()

    mapping = _parse_lot_mapping()
    for keyword, size in mapping.items():
        if keyword.lower() in desc_lower and size in db_sizes:
            return size

    words = desc_lower.split()
    for w in words:
        for s in db_sizes:
            if w == s.lower():
                return s

    return None


def _parse_lot_mapping() -> dict[str, str]:
    raw = settings.funpay_lot_mapping
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("FunPay: invalid FUNPAY_LOT_MAPPING JSON: %s", raw)
        return {}


def _get_chat(acc, username: str):
    try:
        return acc.get_chat_by_name(username, make_request=True)
    except Exception:
        return None


def _generate_code(length: int = 10) -> str:
    return "FP" + "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def _notify_admins(text: str):
    for uid in settings.admin_ids_list:
        try:
            from src.bot.bot import bot
            await bot.send_message(uid, text)
        except Exception:
            pass
