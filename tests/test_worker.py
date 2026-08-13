"""Тесты воркера: relay (публикация outbox-событий) и processor (обработка
+ webhook с ретраями). Брокер — TestRabbitBroker из FastStream (честная
эмуляция протокола в памяти, реальный RabbitMQ не нужен). HTTP для webhook —
подменённый httpx.AsyncClient."""
import httpx
import pytest
from faststream.rabbit import TestRabbitBroker

from app.payments.models import Outbox
from app.payments.repository import OutboxRepository
from app.payments.schemas import PaymentMessage
from app.worker import processor, relay
from app.worker.broker import broker, payments_new


# ---------- relay ----------

async def test_relay_once_publishes_and_marks_events(session_maker, monkeypatch):
    monkeypatch.setattr(relay, "async_session_maker", session_maker)

    published = []

    async def fake_publish(payload, **kwargs):
        published.append(payload)

    monkeypatch.setattr(relay.broker, "publish", fake_publish)

    async with session_maker.begin() as session:
        event = Outbox(aggregate_id=42, event_type="payment.created", payload={"payment_id": 42})
        session.add(event)

    count = await relay.relay_once()

    assert count == 1
    assert published == [{"payment_id": 42}]

    async with session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(select(Outbox).where(Outbox.aggregate_id == 42))
        stored = result.scalar_one()
        assert stored.published_at is not None  # событие помечено опубликованным


async def test_relay_once_returns_zero_when_nothing_pending(session_maker, monkeypatch):
    monkeypatch.setattr(relay, "async_session_maker", session_maker)
    assert await relay.relay_once() == 0


# ---------- processor: send_webhook ----------

class _FakeResponse:
    def __init__(self, ok: bool):
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise httpx.HTTPStatusError("bad status", request=None, response=None)


class _FakeClient:
    def __init__(self, ok: bool, calls: list):
        self.ok = ok
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        self.calls.append(url)
        return _FakeResponse(self.ok)


async def test_send_webhook_succeeds_on_first_try(monkeypatch):
    calls = []
    monkeypatch.setattr(processor.httpx, "AsyncClient", lambda **kw: _FakeClient(ok=True, calls=calls))

    class FakePayment:
        id = 1
        status = "succeeded"
        amount = "10.00"
        currency = "RUB"
        processed_at = None
        webhook_url = "https://example.com/hook"

    await processor.send_webhook(FakePayment())
    assert len(calls) == 1


async def test_send_webhook_retries_and_raises_after_max_attempts(monkeypatch):
    calls = []
    monkeypatch.setattr(processor.httpx, "AsyncClient", lambda **kw: _FakeClient(ok=False, calls=calls))
    # ускоряем ретраи, не дожидаясь реального exponential backoff
    async def no_sleep(*_a, **_kw):
        pass

    monkeypatch.setattr(processor.send_webhook.retry, "sleep", no_sleep)

    class FakePayment:
        id = 1
        status = "failed"
        amount = "10.00"
        currency = "RUB"
        processed_at = None
        webhook_url = "https://example.com/hook"

    with pytest.raises(httpx.HTTPStatusError):
        await processor.send_webhook(FakePayment())

    assert len(calls) == 3  # settings.webhook_max_retries


# ---------- processor: process() handler ----------

async def test_process_skips_webhook_when_payment_not_found(monkeypatch):
    async def not_found(payment_id):
        return None

    monkeypatch.setattr(processor.payment_service, "process_payment", not_found)

    webhook_calls = []

    async def fake_webhook(payment):
        webhook_calls.append(payment)

    monkeypatch.setattr(processor, "send_webhook", fake_webhook)

    await processor.process(PaymentMessage(payment_id=999_999))

    assert webhook_calls == []


async def test_process_sends_webhook_when_payment_found(monkeypatch):
    class FakePayment:
        id = 1

    async def found(payment_id):
        return FakePayment()

    monkeypatch.setattr(processor.payment_service, "process_payment", found)

    webhook_calls = []

    async def fake_webhook(payment):
        webhook_calls.append(payment)

    monkeypatch.setattr(processor, "send_webhook", fake_webhook)

    await processor.process(PaymentMessage(payment_id=1))

    assert len(webhook_calls) == 1


# ---------- сквозная проверка: подписчик реально подключён к очереди ----------

async def test_subscriber_is_wired_to_payments_new_queue(monkeypatch):
    """Публикуем через TestRabbitBroker (эмуляция протокола, не реальный
    RabbitMQ) и проверяем, что декоратор @broker.subscriber(payments_new)
    реально доставляет сообщение в process()."""
    calls = []

    async def fake_process_payment(payment_id):
        calls.append(payment_id)
        return None  # без найденного платежа — webhook не дёрнется, это ок для проверки маршрутизации

    monkeypatch.setattr(processor.payment_service, "process_payment", fake_process_payment)

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish({"payment_id": 777}, queue=payments_new)

    assert calls == [777]
