import asyncio
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
    """Starts the FunPay order listener in a background task."""
    global FUNPAY_ENABLED

    if not settings.funpay_golden_key or not settings.funpay_lot_id:
        logger.info("FunPay: not configured (FUNPAY_GOLDEN_KEY or FUNPAY_LOT_ID missing)")
        return

    FUNPAY_ENABLED = True
    asyncio.create_task(_run_listener())


async def _run_listener():
    """Runs the FunPay event listener loop."""
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
    """Handle a new FunPay order: reserve account, create promo, notify buyer."""
    description = order.description or ""
    price = order.price
    buyer_username = order.buyer_username
    logger.info(
        "FunPay: new order #%s — %s (%.2f ₽) by @%s",
        order.id, description, price, buyer_username,
    )

    size = _detect_size(description)

    async with async_session() as session:
        available = await get_available_accounts_by_size(session, size)
        if not available:
            msg = f"❌ Нет доступных аккаунтов {size} для заказа FunPay #{order.id}"
            logger.warning("FunPay: %s", msg)
            await _notify_admins(msg)
            chat = acc.get_chat_by_name(buyer_username, make_request=True)
            if chat:
                acc.send_message(
                    chat.id,
                    "😕 К сожалению, аккаунты этого тарифа закончились. "
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

        chat = acc.get_chat_by_name(buyer_username, make_request=True)
        if chat:
            acc.send_message(
                chat.id,
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"Ваш промокод: <code>{code}</code>\n\n"
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


def _detect_size(description: str) -> str:
    """Extract size from the order description."""
    desc_lower = description.lower()
    sizes = [
        "standard", "standart", "standart",
        "premium", "премиум",
        "vip",
        "ultra",
        "lite",
        "base",
        "pro",
    ]
    for s in sizes:
        if s in desc_lower:
            return s.capitalize()
    return description.strip() or "Standard"


def _generate_code(length: int = 10) -> str:
    return "FP" + "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def _notify_admins(text: str):
    for uid in settings.admin_ids_list:
        try:
            from src.bot.bot import bot
            await bot.send_message(uid, text)
        except Exception:
            pass
