import asyncio
import random
from datetime import datetime, UTC

from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import async_session_maker
from app.models import Payment, Outbox, PaymentStatus
from app.repository import PaymentRepository, OutboxRepository
from app.schemas import PaymentCreate


class PaymentService:

    def __init__(self, payment_repo: PaymentRepository, outbox_repo: OutboxRepository, session_maker=None):
        # По умолчанию — глобальный session_maker: безопасно для FastAPI/
        # FastStream-процессов с одним живущим вечно event loop. Тесты
        # (TestClient, pytest-asyncio — у каждого свой event loop на вызов/
        # тест) передают свой session_maker на свежем engine, иначе пул
        # соединений глобального engine переживёт закрытие чужого лупа и
        # столкнётся со следующим ("Future attached to a different loop").
        self.payment_repo = payment_repo
        self.outbox_repo = outbox_repo
        self.session_maker = session_maker or async_session_maker

    async def get_payment(self, payment_id: int) -> Payment | None:
        async with self.session_maker() as async_session:
            return await self.payment_repo.get_by_id(async_session, payment_id)

    async def create_payment(self, data: PaymentCreate, idempotency_key: str) -> Payment | None:
        try:
            async with self.session_maker.begin() as async_session:
                if existing := await self.payment_repo.get_by_idempotency_key(async_session, idempotency_key):
                    return existing
                payment = Payment(
                    amount=data.amount,
                    currency=data.currency,
                    description=data.description,
                    meta=data.metadata,
                    idempotency_key=idempotency_key,
                    webhook_url=data.webhook_url, )
                await self.payment_repo.create_payment(async_session, payment)

                event = Outbox(aggregate_id=payment.id,
                               event_type="payment.created",
                               payload={"payment_id": payment.id}, )

                await self.outbox_repo.create_outbox(async_session, event)

                return payment
        except IntegrityError:
            async with self.session_maker() as async_session:
                return await self.payment_repo.get_by_idempotency_key(async_session, idempotency_key)

    async def process_payment(self, payment_id: int) -> Payment | None:
        async with self.session_maker.begin() as async_session:
            if not (payment := await self.payment_repo.get_by_id(async_session, payment_id)):
                return None
            if payment.status is not PaymentStatus.PENDING:
                return payment

            await asyncio.sleep(random.uniform(settings.process_min_seconds, settings.process_max_seconds))
            failed = random.random() < settings.failure_rate
            payment.status = PaymentStatus.FAILED if failed else PaymentStatus.SUCCEEDED
            payment.processed_at = datetime.now(UTC)
            return payment
