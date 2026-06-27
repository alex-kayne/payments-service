import asyncio
from faststream import FastStream
from app.worker.broker import broker, declare_dlq
from app.worker.relay import run_relay
from app.worker import processor

app = FastStream(broker)

@app.after_startup
async def startup() -> None:
    await declare_dlq()
    asyncio.create_task(run_relay())