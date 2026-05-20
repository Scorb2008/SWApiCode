import asyncio
import html
import json
import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request

from src.config import settings
from src.db.database import async_session
from src.db.repository import (
    create_purchase,
    delete_pending_payment,
    get_all_pending_payments,
    get_or_create_user,
    get_purchase_by_payment_id,
    get_user_by_telegram_id,
    reserve_and_sell_accounts,
)
from src.services.funpay import start_funpay_listener
from src.services.yookassa import get_payment_status, register_webhook

logger = logging.getLogger(__name__)


async def _register_webhook_on_start():
    result = await register_webhook()
    if result.get("ok"):
        note = result.get("note", "")
        logger.info("Webhook registered %s", f"({note})" if note else "")
    else:
        logger.warning("Webhook registration failed: %s", result.get("error"))


async def _reconcile_payments():
    while True:
        await asyncio.sleep(300)
        try:
            async with async_session() as session:
                pending = await get_all_pending_payments(session)

            for pp in pending:
                try:
                    data = await get_payment_status(pp.payment_id)
                except Exception:
                    continue

                status = data.get("status")
                if status == "succeeded":
                    async with async_session() as session:
                        existing = await get_purchase_by_payment_id(session, pp.payment_id)
                        if existing:
                            await delete_pending_payment(session, pp.payment_id)
                            continue

                        user = await get_or_create_user(session, pp.telegram_id)

                        if pp.action == "purchase":
                            metadata = data.get("metadata", {}) or {}
                            size = metadata.get("size")
                            quantity = int(metadata.get("quantity", "1"))
                            total = Decimal(metadata.get("total", "0"))

                            if not size:
                                logger.warning("Reconcile: missing size metadata for %s", pp.payment_id)
                                continue

                            try:
                                accounts = await reserve_and_sell_accounts(
                                    session, size, quantity, user.id, total
                                )
                                for acc in accounts:
                                    purchase = await create_purchase(
                                        session, user.id, acc.price, "yookassa", pp.payment_id
                                    )
                                    purchase.account_id = acc.id
                                await session.commit()
                                await delete_pending_payment(session, pp.payment_id)

                                creds_lines = [
                                    f"🔑 Логин: <code>{html.escape(a.login)}</code>\n🔐 Пароль: <code>{html.escape(a.password)}</code>"
                                    for a in accounts[:3]
                                ]
                                creds_text = "\n\n".join(creds_lines)
                                if len(accounts) > 3:
                                    creds_text += f"\n\n... и ещё {len(accounts) - 3} аккаунтов"

                                await _notify_user(
                                    pp.telegram_id,
                                    f"✅ <b>Покупка успешна!</b>\n\n"
                                    f"{creds_text}\n\n"
                                    f"💵 Списано: {total:.2f} ₽\n"
                                    f"ℹ️ <b>Сайт для входа: https://codex.sale</b>",
                                )
                                await _notify_admins(
                                    f"💰 <b>Покупка через ЮKassa</b>\n\n"
                                    f"👤 Пользователь: <code>{pp.telegram_id}</code>\n"
                                    f"💎 Тариф: {size} x{quantity}\n"
                                    f"💵 Сумма: {total:.2f} ₽"
                                )
                                logger.info("Reconcile: fulfilled purchase %s for user %s", pp.payment_id, pp.telegram_id)
                            except ValueError:
                                await create_purchase(
                                    session, user.id, pp.amount, "yookassa_refund", pp.payment_id
                                )
                                user.balance += pp.amount
                                await session.commit()
                                await delete_pending_payment(session, pp.payment_id)
                                await _notify_user(
                                    pp.telegram_id,
                                    "❌ Аккаунты закончились. Средства возвращены на баланс.",
                                )
                                logger.info("Reconcile: refunded %s for user %s", pp.amount, pp.telegram_id)

                        else:
                            user.balance += pp.amount
                            await create_purchase(
                                session, user.id, pp.amount, "yookassa_topup", pp.payment_id
                            )
                            await session.commit()
                            await delete_pending_payment(session, pp.payment_id)
                            try:
                                from src.bot.bot import bot
                                await bot.send_message(
                                    pp.telegram_id,
                                    f"✅ <b>Баланс пополнен на {pp.amount:.2f} ₽</b>",
                                )
                            except Exception:
                                pass
                            logger.info("Reconcile: credited %s for user %s", pp.amount, pp.telegram_id)

                elif status == "canceled":
                    async with async_session() as session:
                        await delete_pending_payment(session, pp.payment_id)
                    logger.info("Reconcile: removed canceled payment %s", pp.payment_id)
        except Exception as e:
            logger.error("Reconcile error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_reconcile_payments())
    await start_funpay_listener()
    await _register_webhook_on_start()
    yield
    task.cancel()


app = FastAPI(title="SWApiCode Webhook", lifespan=lifespan)


async def _notify_admins(text: str):
    for uid in settings.admin_ids_list:
        try:
            from src.bot.bot import bot
            await bot.send_message(uid, text)
        except Exception:
            pass


async def _notify_user(telegram_id: int, text: str):
    try:
        from src.bot.bot import bot
        await bot.send_message(telegram_id, text)
    except Exception:
        pass


@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    body = await request.body()
    data = json.loads(body)

    event = data.get("event")
    if event not in ("payment.waiting_for_capture", "payment.succeeded"):
        return {"status": "ignored"}

    payment = data.get("object", {})
    payment_id = payment.get("id")
    payment_status = payment.get("status")

    if payment_status != "succeeded":
        return {"status": "not_succeeded"}

    metadata = payment.get("metadata", {}) or {}
    telegram_id = metadata.get("telegram_id")
    action = metadata.get("action", "topup")

    if not telegram_id:
        return {"status": "no_metadata"}

    telegram_id = int(telegram_id)
    amount = Decimal(str(payment["amount"]["value"]))

    async with async_session() as session:
        user = await get_user_by_telegram_id(session, telegram_id)
        if not user:
            user = await get_or_create_user(session, telegram_id, None, None)

        await delete_pending_payment(session, payment_id)

        if action == "purchase":
            size = metadata.get("size")
            quantity = int(metadata.get("quantity", "1"))
            total = Decimal(metadata.get("total", "0"))

            try:
                accounts = await reserve_and_sell_accounts(
                    session, size, quantity, user.id, total
                )
                for acc in accounts:
                    purchase = await create_purchase(
                        session, user.id, acc.price, "yookassa", payment_id
                    )
                    purchase.account_id = acc.id
                await session.commit()

                creds_lines = [f"🔑 Логин: <code>{a.login}</code>\n🔐 Пароль: <code>{a.password}</code>" for a in accounts[:3]]
                creds_text = "\n\n".join(creds_lines)
                if len(accounts) > 3:
                    creds_text += f"\n\n... и ещё {len(accounts) - 3} аккаунтов"
                await _notify_user(
                    telegram_id,
                    f"✅ <b>Покупка успешна!</b>\n\n"
                    f"{creds_text}\n\n"
                    f"💵 Списано: {total:.2f} ₽\n"
                    f"ℹ️ <b>Сайт для входа: https://codex.sale</b>",
                )
                await _notify_admins(
                    f"💰 <b>Покупка через ЮKassa</b>\n\n"
                    f"👤 Пользователь: <code>{telegram_id}</code>\n"
                    f"💎 Тариф: {size} x{quantity}\n"
                    f"💵 Сумма: {total:.2f} ₽"
                )
            except ValueError:
                await create_purchase(
                    session, user.id, amount, "yookassa_refund", payment_id
                )
                user.balance += amount
                await session.commit()
                await _notify_user(
                    telegram_id,
                    "❌ Аккаунты закончились. Средства возвращены на баланс.",
                )
                return {"status": "accounts_unavailable", "credited": True}

        else:
            user.balance += amount
            await create_purchase(
                session, user.id, amount, "yookassa_topup", payment_id
            )
            await session.commit()

            await _notify_user(
                telegram_id,
                f"✅ <b>Баланс пополнен на {amount:.2f} ₽</b>",
            )
            await _notify_admins(
                f"💰 <b>Пополнение баланса</b>\n\n"
                f"👤 Пользователь: <code>{telegram_id}</code>\n"
                f"💵 Сумма: {amount:.2f} ₽"
            )

    return {"status": "ok"}
