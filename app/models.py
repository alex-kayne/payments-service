from datetime import datetime, UTC
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Base(DeclarativeBase):
    ...


class Payments(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float] = mapped_column(Numeric)
    currency: Mapped[Currency]
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[JSONB | JSONB] = mapped_column("metadata", JSONB, default=dict)
    status: Mapped[PaymentStatus]
    idempotency_key: str = mapped_column(Text)
    webhook_url: str = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class Outbox(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    aggregate_id: Mapped[int] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[JSONB] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
