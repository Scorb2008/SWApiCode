import json
from decimal import Decimal

from fastapi import FastAPI, Request

from src.config import settings
from src.db.database import async_session
from src.db.repository import (
    create_purchase,
    get_or_create_user,
    get_user_by_telegram_id,
    reserve_and_sell_accounts,
)

app = FastAPI(title="SWApiCode Webhook")


async def _notify_admins(text: str):
    for uid in settings.admin_ids_list:
        try:
            from src.bot.bot import bot
            await bot.send_message(uid, text)
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
                    session.add(purchase)
                await session.commit()

                await _notify_admins(
                    f"💰 <b>Покупка через ЮKassa</b>\n\n"
                    f"👤 Пользователь: <code>{telegram_id}</code>\n"
                    f"💎 Тариф: {size} x{quantity}\n"
                    f"💵 Сумма: {total:.2f} ₽"
                )
            except ValueError:
                user.balance += amount
                await session.commit()
                await create_purchase(
                    session, user.id, amount, "yookassa_refund", payment_id
                )
                return {"status": "accounts_unavailable", "credited": True}

        else:
            user.balance += amount
            await create_purchase(
                session, user.id, amount, "yookassa_topup", payment_id
            )
            await session.commit()

            await _notify_admins(
                f"💰 <b>Пополнение баланса</b>\n\n"
                f"👤 Пользователь: <code>{telegram_id}</code>\n"
                f"💵 Сумма: {amount:.2f} ₽"
            )

    return {"status": "ok"}
