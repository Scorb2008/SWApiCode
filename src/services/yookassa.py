import uuid

import httpx

from src.config import settings

YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


def _auth():
    return (settings.yookassa_shop_id, settings.yookassa_secret_key)


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


async def get_payment_status(payment_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YOOKASSA_API_URL}/payments/{payment_id}",
            auth=_auth(),
        )
    response.raise_for_status()
    return response.json()
