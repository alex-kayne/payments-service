from fastapi import FastAPI
from app.api.payments import router as payments_router

app = FastAPI(title="payments-service")
app.include_router(payments_router)
