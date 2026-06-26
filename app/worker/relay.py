import asyncio
import logging

from app.config import settings
from app.database import async_session_maker
from app.repository import OutboxRepository
from app.worker.broker import broker, payments_new

outbox_repo = OutboxRepository()


async def relay_once() -> int:
    async with async_session_maker.begin() as async_session:
        events = await outbox_repo.fetch_unpublished(async_session, settings.outbox_batch_size)
        for event in events:
            await broker.publish(event.payload, queue=payments_new, persist=True)
            await outbox_repo.mark_published(event)
        return len(events)


async def run_relay() -> None:
    while True:
        try:
            published = await relay_once()
        except Exception:
            logging.exception("relay iteration failed")
            published = 0
        if published == 0:
            await asyncio.sleep(settings.outbox_poll_interval)
