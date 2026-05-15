from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Account, PromoCode, Purchase, User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
) -> User:
    user = User(telegram_id=telegram_id, username=username, full_name=full_name)
    session.add(user)
    await session.commit()
    return user


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    full_name: str | None = None,
) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user:
        return user
    return await create_user(session, telegram_id, username, full_name)


async def update_balance(
    session: AsyncSession, user_id: int, amount: Decimal
) -> User:
    user = await session.get(User, user_id)
    user.balance = user.balance + amount
    await session.commit()
    return user


async def set_balance(
    session: AsyncSession, user_id: int, amount: Decimal
) -> User:
    user = await session.get(User, user_id)
    user.balance = amount
    await session.commit()
    return user


async def set_ban_status(session: AsyncSession, user_id: int, banned: bool) -> User:
    user = await session.get(User, user_id)
    user.is_banned = banned
    await session.commit()
    return user


async def get_all_users(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.registered_at.desc()))
    return result.scalars().all()


async def get_users_paginated(
    session: AsyncSession, offset: int = 0, limit: int = 10
) -> Sequence[User]:
    result = await session.execute(
        select(User).order_by(User.registered_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


async def get_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar() or 0


async def search_users(
    session: AsyncSession, query: str
) -> Sequence[User]:
    q = query.strip().lstrip("@")
    try:
        tid = int(q)
        user = await get_user_by_telegram_id(session, tid)
        return [user] if user else []
    except ValueError:
        pass

    pattern = f"%{q.lower()}%"
    result = await session.execute(
        select(User).where(func.lower(User.username).like(pattern))
    )
    return result.scalars().all()


async def get_account_by_login(session: AsyncSession, login: str) -> Account | None:
    result = await session.execute(select(Account).where(Account.login == login))
    return result.scalar_one_or_none()


async def bulk_insert_accounts(
    session: AsyncSession, accounts: list[dict]
) -> tuple[int, int]:
    added = 0
    skipped = 0
    for data in accounts:
        exists = await get_account_by_login(session, data["login"])
        if exists:
            skipped += 1
            continue
        status = data.get("status", "").strip().lower()
        is_sold = status == "продан"
        account = Account(
            login=data["login"],
            password=data["password"],
            size=data["size"],
            price=Decimal(str(data["price"])).quantize(Decimal("0.01")),
            status="sold" if is_sold else "available",
        )
        session.add(account)
        added += 1
    await session.commit()
    return added, skipped


async def get_available_accounts_by_size(
    session: AsyncSession, size: str
) -> Sequence[Account]:
    result = await session.execute(
        select(Account)
        .where(Account.size == size, Account.status == "available")
        .order_by(Account.id)
    )
    return result.scalars().all()


async def get_available_count_by_size(session: AsyncSession) -> list[tuple[str, int]]:
    result = await session.execute(
        select(Account.size, func.count(Account.id))
        .where(Account.status == "available")
        .group_by(Account.size)
        .order_by(Account.size)
    )
    return result.all()


async def get_total_accounts_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Account.id)))
    return result.scalar() or 0


async def get_accounts_count_by_status(session: AsyncSession, status: str) -> int:
    result = await session.execute(
        select(func.count(Account.id)).where(Account.status == status)
    )
    return result.scalar() or 0


async def get_accounts_count_by_size_and_status(
    session: AsyncSession, size: str, status: str
) -> int:
    result = await session.execute(
        select(func.count(Account.id)).where(
            Account.size == size, Account.status == status
        )
    )
    return result.scalar() or 0


async def get_total_revenue(session: AsyncSession) -> Decimal:
    result = await session.execute(select(func.sum(Purchase.amount)))
    return result.scalar() or Decimal("0")


async def get_active_promos_count(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(PromoCode.id)).where(PromoCode.is_active.is_(True))
    )
    return result.scalar() or 0


async def get_sizes_list(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(Account.size).distinct().order_by(Account.size)
    )
    return [r[0] for r in result.all()]


async def reserve_and_sell_accounts(
    session: AsyncSession,
    size: str,
    quantity: int,
    user_id: int,
    total_price: Decimal,
) -> list[Account]:
    result = await session.execute(
        select(Account)
        .where(Account.size == size, Account.status == "available")
        .order_by(Account.id)
        .limit(quantity)
        .with_for_update()
    )
    accounts = list(result.scalars().all())
    if len(accounts) < quantity:
        raise ValueError("Not enough available accounts")

    now = datetime.now()
    for acc in accounts:
        acc.status = "sold"
        acc.sold_to_user_id = user_id
        acc.sold_at = now

    await session.commit()
    return accounts


async def create_purchase(
    session: AsyncSession,
    user_id: int,
    amount: Decimal,
    payment_method: str,
    payment_id: str | None = None,
) -> Purchase:
    purchase = Purchase(
        user_id=user_id,
        amount=amount,
        payment_method=payment_method,
        payment_id=payment_id,
    )
    session.add(purchase)
    return purchase


async def get_purchases_by_user(
    session: AsyncSession, user_id: int
) -> Sequence[Purchase]:
    result = await session.execute(
        select(Purchase)
        .where(Purchase.user_id == user_id)
        .order_by(Purchase.created_at.desc())
    )
    return result.scalars().all()


async def get_purchase_count_by_user(
    session: AsyncSession, user_id: int
) -> int:
    result = await session.execute(
        select(func.count(Purchase.id)).where(Purchase.user_id == user_id)
    )
    return result.scalar() or 0


async def get_revenue_by_payment_method(session: AsyncSession) -> list[tuple[str, Decimal]]:
    result = await session.execute(
        select(Purchase.payment_method, func.sum(Purchase.amount))
        .group_by(Purchase.payment_method)
        .order_by(func.sum(Purchase.amount).desc())
    )
    return result.all()


async def get_revenue_last_days(session: AsyncSession, days: int) -> Decimal:
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(days=days)
    result = await session.execute(
        select(func.sum(Purchase.amount)).where(Purchase.created_at >= since)
    )
    return result.scalar() or Decimal("0")


async def get_promo_by_code(session: AsyncSession, code: str) -> PromoCode | None:
    result = await session.execute(
        select(PromoCode).where(PromoCode.code == code, PromoCode.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def use_promo(session: AsyncSession, promo: PromoCode) -> PromoCode:
    promo.used_count += 1
    if promo.used_count >= promo.max_uses:
        promo.is_active = False
    await session.commit()
    return promo


async def create_promo(
    session: AsyncSession,
    code: str,
    promo_type: str,
    value: Decimal,
    max_uses: int = 1,
    token_value: str | None = None,
) -> PromoCode:
    promo = PromoCode(
        code=code,
        promo_type=promo_type,
        value=value,
        max_uses=max_uses,
        token_value=token_value,
    )
    session.add(promo)
    await session.commit()
    return promo


async def get_all_promos(session: AsyncSession) -> Sequence[PromoCode]:
    result = await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
    return result.scalars().all()


async def get_promos_paginated(
    session: AsyncSession, offset: int = 0, limit: int = 8
) -> Sequence[PromoCode]:
    result = await session.execute(
        select(PromoCode).order_by(PromoCode.created_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


async def get_promos_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(PromoCode.id)))
    return result.scalar() or 0


async def delete_promo(session: AsyncSession, promo_id: int) -> bool:
    promo = await session.get(PromoCode, promo_id)
    if not promo:
        return False
    await session.delete(promo)
    await session.commit()
    return True
