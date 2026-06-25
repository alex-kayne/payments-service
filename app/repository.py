from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Outbox


class PaymentRepository:
    async def get_by_id(self, async_session: AsyncSession, payment_id: int) -> Payment | None:
        return await async_session.get(Payment, payment_id)

    async def get_by_idempotency_key(self, async_session: AsyncSession, idempotency_key: int) -> Payment | None:
        stmt = select(Payment).where(Payment.idempotency_key == idempotency_key)
        result = await async_session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_payment(self, async_session: AsyncSession, payment: Payment) -> Payment | None:
        async_session.add(payment)
        await async_session.flush()


class OutboxRepository:

    async def create_outbox(self, async_session: AsyncSession, event: Outbox) -> None:
        async_session.add(event)

    async def fetch_unpublished(self, async_session: AsyncSession, limit: int) -> Sequence[Outbox]:
        stmt = select(Outbox).where(Outbox.published_at.is_(None)).order_by(Outbox.created_at).limit(
            limit).with_for_update(skip_locked=True)
        result = await async_session.execute(stmt)
        return result.scalars().all()
