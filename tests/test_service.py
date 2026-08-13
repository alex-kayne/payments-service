"""Тесты сервисного слоя на настоящем Postgres (см. conftest.session_maker).
Покрывают идемпотентность создания платежа и переходы статуса при обработке —
то, что явно оценивается в ТЗ."""
from decimal import Decimal

import pytest

from app.payments.models import Currency, PaymentStatus
from app.payments.repository import PaymentRepository, OutboxRepository
from app.payments.schemas import PaymentCreate
from app.payments.service import PaymentService


def _create_data(**overrides) -> PaymentCreate:
    payload = {
        "amount": Decimal("100.50"),
        "currency": Currency.RUB,
        "description": "test",
        "metadata": {"order_id": 1},
        "webhook_url": "https://example.com/hook",
    }
    payload.update(overrides)
    return PaymentCreate(**payload)


def _service(session_maker) -> PaymentService:
    return PaymentService(PaymentRepository(), OutboxRepository(), session_maker=session_maker)


async def test_create_payment_writes_payment_and_outbox_event(session_maker):
    service = _service(session_maker)
    payment = await service.create_payment(_create_data(), idempotency_key="key-1")

    assert payment.status == PaymentStatus.PENDING
    assert payment.id is not None

    async with session_maker() as session:
        from sqlalchemy import select
        from app.payments.models import Outbox
        result = await session.execute(select(Outbox).where(Outbox.aggregate_id == payment.id))
        event = result.scalar_one()
        assert event.event_type == "payment.created"
        assert event.payload == {"payment_id": payment.id}
        assert event.published_at is None


async def test_create_payment_idempotent_on_repeat(session_maker):
    service = _service(session_maker)
    first = await service.create_payment(_create_data(), idempotency_key="key-2")
    second = await service.create_payment(_create_data(), idempotency_key="key-2")

    assert first.id == second.id

    async with session_maker() as session:
        from sqlalchemy import func, select
        from app.payments.models import Payment
        total = await session.scalar(select(func.count()).select_from(Payment))
        assert total == 1


async def test_get_payment_returns_none_when_missing(session_maker):
    service = _service(session_maker)
    assert await service.get_payment(999_999) is None


async def test_process_payment_transitions_to_terminal_status(session_maker, monkeypatch):
    import app.payments.service as service_module

    async def no_sleep(*_a, **_kw):
        pass

    monkeypatch.setattr(service_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(service_module.random, "random", lambda: 0.99)  # > failure_rate -> succeeded

    service = _service(session_maker)
    created = await service.create_payment(_create_data(), idempotency_key="key-3")
    processed = await service.process_payment(created.id)

    assert processed.status == PaymentStatus.SUCCEEDED
    assert processed.processed_at is not None


async def test_process_payment_skips_already_terminal_payment(session_maker, monkeypatch):
    import app.payments.service as service_module

    async def no_sleep(*_a, **_kw):
        pass

    monkeypatch.setattr(service_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(service_module.random, "random", lambda: 0.0)  # < failure_rate -> failed

    service = _service(session_maker)
    created = await service.create_payment(_create_data(), idempotency_key="key-4")
    first = await service.process_payment(created.id)
    assert first.status == PaymentStatus.FAILED
    first_processed_at = first.processed_at

    # повторная обработка (дубль сообщения из очереди) не должна пере-рандомить исход
    second = await service.process_payment(created.id)
    assert second.status == PaymentStatus.FAILED
    assert second.processed_at == first_processed_at


async def test_process_payment_returns_none_when_missing(session_maker):
    service = _service(session_maker)
    assert await service.process_payment(999_999) is None
