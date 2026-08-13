from app.payments.repository import PaymentRepository, OutboxRepository

from app.payments.service import PaymentService


def get_payment_service() -> PaymentService:
    return PaymentService(PaymentRepository(), OutboxRepository())
