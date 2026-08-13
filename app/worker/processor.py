import logging

import httpx
from faststream import AckPolicy
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.payments.models import Payment
from app.payments.repository import PaymentRepository, OutboxRepository
from app.payments.schemas import WebhookPayload, PaymentMessage
from app.payments.service import PaymentService
from app.worker.broker import broker, payments_new

payment_service = PaymentService(PaymentRepository(), OutboxRepository())


@retry(
    stop=stop_after_attempt(settings.webhook_max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def send_webhook(payment: Payment) -> None:
    payload = WebhookPayload.model_validate(payment).model_dump(mode="json")
    async with httpx.AsyncClient(timeout=settings.webhook_timeout) as client:
        response = await client.post(payment.webhook_url, json=payload)
        response.raise_for_status()

@broker.subscriber(payments_new, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def process(message: PaymentMessage) -> None:
    if not (payment := await payment_service.process_payment(message.payment_id)):
        logging.warning(f"Payment {message.payment_id} not found")
        return
    await send_webhook(payment)

