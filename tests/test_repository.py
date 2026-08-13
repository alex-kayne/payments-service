"""Тесты репозиториев на настоящем Postgres — в частности FOR UPDATE SKIP
LOCKED в fetch_unpublished, критичный для корректной работы relay при
нескольких воркерах (не дублировать публикацию одного и того же события)."""
from app.payments.models import Payment, Currency, PaymentStatus, Outbox
from app.payments.repository import PaymentRepository, OutboxRepository


async def _make_payment(session_maker, idempotency_key: str) -> Payment:
    async with session_maker.begin() as session:
        payment = Payment(
            amount="10.00",
            currency=Currency.RUB,
            idempotency_key=idempotency_key,
            webhook_url="https://example.com",
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
    return payment_id


async def test_get_by_idempotency_key_finds_existing(session_maker):
    repo = PaymentRepository()
    payment_id = await _make_payment(session_maker, "key-a")

    async with session_maker() as session:
        found = await repo.get_by_idempotency_key(session, "key-a")
        assert found.id == payment_id
        assert await repo.get_by_idempotency_key(session, "does-not-exist") is None


async def test_fetch_unpublished_skips_locked_rows(session_maker):
    """Два конкурентных SELECT ... FOR UPDATE SKIP LOCKED на одну и ту же
    неопубликованную строку не должны получить одну и ту же строку дважды —
    иначе два relay-воркера опубликуют одно событие два раза."""
    repo = OutboxRepository()
    async with session_maker.begin() as setup_session:
        event = Outbox(aggregate_id=1, event_type="payment.created", payload={"payment_id": 1})
        setup_session.add(event)

    # первая "транзакция" держит лок, не коммитя
    session_a = session_maker()
    await session_a.begin()
    locked_by_a = await repo.fetch_unpublished(session_a, limit=10)
    assert len(locked_by_a) == 1

    # вторая транзакция не должна увидеть ту же строку, пока первая её держит
    async with session_maker() as session_b:
        seen_by_b = await repo.fetch_unpublished(session_b, limit=10)
        assert seen_by_b == []

    await session_a.rollback()
    await session_a.close()


async def test_mark_published_sets_timestamp(session_maker):
    repo = OutboxRepository()
    async with session_maker.begin() as session:
        event = Outbox(aggregate_id=1, event_type="payment.created", payload={"payment_id": 1})
        session.add(event)
        await session.flush()
        assert event.published_at is None
        await repo.mark_published(event)
        assert event.published_at is not None
