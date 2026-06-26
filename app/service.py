from sqlalchemy.exc import IntegrityError

from app.database import async_session_maker
from app.models import Payment, Outbox
from app.repository import PaymentRepository, OutboxRepository
from app.schemas import PaymentCreate


class PaymentService:

    def __init__(self, payment_repo: PaymentRepository, outbox_repo: OutboxRepository):
        self.payment_repo = payment_repo
        self.outbox_repo = outbox_repo

    async def create_payment(self, data: PaymentCreate, idempotency_key: str) -> Payment:
        async with async_session_maker() as async_session:
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
