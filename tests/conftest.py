"""Общие фикстуры. Тестовая стратегия: реальный Postgres (docker-compose
инфраструктура проекта), не in-memory SQLite — модели используют
postgres-специфичные Enum(values_callable) и JSONB. Брокер — TestRabbitBroker
из FastStream (честная эмуляция протокола без сети, не самодельный мок).

Фикстура session_maker создаётся СИНХРОННОЙ (без async def): create_async_engine
ленив и не требует активного event loop на конструирование. Первое реальное
использование движка происходит там, где объект реально нужен (тело теста
или портал TestClient), и привязывается к правильному лупу. Если бы фикстура
сама была async, engine получил бы соединения в лупе pytest-asyncio, а
использовался бы потом в ДРУГОМ лупе (например, портале TestClient) —
поймали бы 'Future attached to a different loop', с которой уже сталкивались
на предыдущих проектах с Celery-таской и с TestClient в file-catalog-downloader.
"""
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings


async def _truncate_and_reset_pool(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE payment, outbox RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture()
def session_maker():
    engine = create_async_engine(settings.database_url)
    asyncio.run(_truncate_and_reset_pool(engine))
    yield async_sessionmaker(engine, expire_on_commit=False)
    try:
        asyncio.run(engine.dispose())
    except RuntimeError:
        pass
