from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.models import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Currency
    description: str | None = None
    metadata: dict = Field(default_factory=dict)
    webhook_url: str


class PaymentCreateResponse(BaseModel):
    payment_id: int = Field(validation_alias="id")
    status: PaymentStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentRead(BaseModel):
    payment_id: int = Field(validation_alias="id")
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict = Field(validation_alias="meta")
    status: PaymentStatus
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class WebhookPayload(BaseModel):
    payment_id: int = Field(validation_alias="id")
    status: PaymentStatus
    amount: Decimal
    currency: Currency
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class PaymentMessage(BaseModel):
    payment_id: int
