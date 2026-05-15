import uuid

import httpx

from src.config import settings

YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


def _auth():
    return (settings.yookassa_shop_id, settings.yookassa_secret_key)


WEBHOOK_EVENT = "payment.succeeded"


async def register_webhook() -> dict:
    result = {"ok": False, "error": None}
    if not settings.public_url:
        result["error"] = "PUBLIC_URL not configured"
        return result
    webhook_url = f"{settings.public_url.rstrip('/')}/yookassa/webhook"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{YOOKASSA_API_URL}/webhooks",
                json={
                    "event": WEBHOOK_EVENT,
                    "url": webhook_url,
                },
                auth=_auth(),
                headers={"Idempotence-Key": str(uuid.uuid4())},
            )
        if response.status_code in (200, 201):
            result["ok"] = True
        elif response.status_code == 409:
            result["ok"] = True
            result["note"] = "already registered"
        else:
            result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        result["error"] = str(e)
    return result


async def create_yookassa_payment(
    amount: float,
    description: str,
    metadata: dict | None = None,
    return_url: str = "https://t.me/",
) -> tuple[str, str]:
    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "capture": True,
        "description": description,
    }
    if metadata:
        payload["metadata"] = metadata

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{YOOKASSA_API_URL}/payments",
            json=payload,
            auth=_auth(),
            headers={"Idempotence-Key": idempotence_key},
        )

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"YooKassa error {response.status_code}: {response.text}"
        )

    data = response.json()
    payment_url = data["confirmation"]["confirmation_url"]
    payment_id = data["id"]
    return payment_url, payment_id


async def check_yookassa_connection() -> dict:
    result = {"ok": False, "shop_id": settings.yookassa_shop_id, "error": None}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{YOOKASSA_API_URL}/payments",
                auth=_auth(),
                params={"limit": 1},
            )
        if response.status_code == 200:
            result["ok"] = True
        else:
            result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        result["error"] = str(e)
    return result


async def get_payment_status(payment_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YOOKASSA_API_URL}/payments/{payment_id}",
            auth=_auth(),
        )
    response.raise_for_status()
    return response.json()
