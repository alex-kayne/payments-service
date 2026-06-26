from fastapi import APIRouter, Depends, status, Header, HTTPException

from app.api import deps
from app.schemas import PaymentCreateResponse, PaymentCreate, PaymentRead
from app.service import PaymentService

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(deps.get_payment_service)]
)


@router.post("", status_code=status.HTTP_202_CREATED, response_model=PaymentCreateResponse)
async def create_payment(
        data: PaymentCreate,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        service: PaymentService = Depends(deps.get_payment_service),
):
    return service.create_payment(data, idempotency_key)


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment(
        payment_id: int,
        service: PaymentService = Depends(deps.get_payment_service),
):
    payment = await service.get_payment(payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment
