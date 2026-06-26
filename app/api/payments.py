from fastapi import APIRouter, Depends, status, Header, HTTPException

from app.api.deps import get_payment_service
from app.schemas import PaymentCreateResponse, PaymentCreate, PaymentRead
from app.security import verify_api_key
from app.service import PaymentService

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(verify_api_key)]
)


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=PaymentCreateResponse)
async def create_payment(
        data: PaymentCreate,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        service: PaymentService = Depends(get_payment_service),
):
    return await service.create_payment(data, idempotency_key)


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment(
        payment_id: int,
        service: PaymentService = Depends(get_payment_service),
):
    payment = await service.get_payment(payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment
