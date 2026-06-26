from app.repository import PaymentRepository, OutboxRepository

from app.service import PaymentService


def get_payment_service() -> PaymentService:
    return PaymentService(PaymentRepository(), OutboxRepository())
