# payments-service

Асинхронный сервис обработки платежей. Принимает запрос на оплату, публикует
событие через Outbox pattern, обрабатывает платёж в фоновом consumer'е через
RabbitMQ и уведомляет клиента о результате через webhook.

## Стек

FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), PostgreSQL, RabbitMQ (FastStream),
Alembic, Docker.

## Запуск

```
cp .env.example .env
docker compose up --build
```

Поднимаются `postgres`, `rabbitmq`, `api`, `consumer`. Миграции накатываются
автоматически при старте `api`.

- API — http://localhost:8000
- Swagger — http://localhost:8000/docs
- RabbitMQ management UI — http://localhost:15672 (guest / guest)
- Health check — http://localhost:8000/health

## Тесты

```
poetry install
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/payments \
RABBITMQ_URL=amqp://guest:guest@localhost:5672/ \
poetry run pytest
```

Требуется поднятый Postgres (`docker compose up postgres -d` или локальный).
RabbitMQ для тестов не нужен — брокер эмулируется через `TestRabbitBroker`
(часть FastStream), реальной сети нет.

Покрытие: repository (включая `SELECT ... FOR UPDATE SKIP LOCKED` на
конкурентных транзакциях), service (идемпотентность создания, переходы
статуса), API (аутентификация, коды ответов, идемпотентный повтор), worker
(relay, retry вебхука, маршрутизация сообщения к подписчику через реальный
протокол RabbitMQ в памяти).

## API

Все запросы требуют заголовок `X-API-Key`.

**Создать платёж** — `POST /api/v1/payments`, заголовок `Idempotency-Key`
обязателен:

```
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: super-secret-key" \
  -H "Idempotency-Key: 7c1f9a3e-2b6d-4f10-9a0c-1e2d3f4a5b6c" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Заказ #123",
    "metadata": {"order_id": 123},
    "webhook_url": "https://webhook.site/your-uuid"
  }'
```

Ответ `202 Accepted`:

```json
{
  "payment_id": 1,
  "status": "pending",
  "created_at": "2026-06-24T10:15:00Z"
}
```

**Получить платёж** — `GET /api/v1/payments/{payment_id}` → `200` с полной
информацией о платеже, `404` если не найден.

**Webhook** — на `webhook_url` приходит `POST` с результатом обработки:

```json
{
  "payment_id": 1,
  "status": "succeeded",
  "amount": "100.50",
  "currency": "RUB",
  "processed_at": "2026-06-24T10:15:04Z"
}
```

## Структура проекта

```
app/
├── main.py              # точка входа FastAPI, /health
├── config.py             # настройки из окружения (pydantic-settings)
├── database.py            # async engine + session maker
├── models.py               # ORM: Payment, Outbox, enums статусов
├── schemas.py               # Pydantic-схемы запросов/ответов
├── security.py               # проверка X-API-Key
├── repository.py               # доступ к данным (PaymentRepository, OutboxRepository)
├── service.py                   # бизнес-логика (PaymentService)
├── api/
│   ├── payments.py               # HTTP-роуты
│   └── deps.py                    # DI: сборка PaymentService
└── worker/
    ├── broker.py                   # RabbitMQ: очереди, DLX/DLQ
    ├── relay.py                     # публикация outbox-событий в очередь
    ├── processor.py                  # обработка платежа + webhook с ретраями
    └── app.py                         # точка входа FastStream (consumer)
alembic/                                # миграции БД
tests/
├── conftest.py                          # фикстура session_maker (реальный Postgres)
├── test_repository.py
├── test_service.py
├── test_api.py
└── test_worker.py
```

Два входа в приложение (`api/` — HTTP, `worker/` — фоновая обработка) стоят
на общем слое `repository`/`service`: платёж создаётся через API, обрабатывается
через consumer, логика между ними не дублируется.

## Как это работает

**Outbox.** При создании платежа `Payment` и запись в `outbox` пишутся в
одной транзакции. Отдельная корутина (`relay`, работает внутри процесса
`consumer`) вычитывает неопубликованные события через
`SELECT ... FOR UPDATE SKIP LOCKED` и публикует их в очередь `payments.new`.
Событие не теряется, даже если в момент создания платежа RabbitMQ был
недоступен.

**Обработка.** `consumer` читает `payments.new`, эмулирует обработку
(2–5 сек, 90% успех / 10% отказ), обновляет статус и отправляет webhook.
Доставку ретраит 3 раза с экспоненциальной задержкой (`tenacity`). Если
доставить не удалось — сообщение уходит в `payments.dlq` через
dead-letter exchange `payments.dlx`.

**Идемпотентность.**
- На создании — уникальный `Idempotency-Key`; повторный запрос с тем же
  ключом возвращает уже созданный платёж, а не создаёт новый.
- В consumer'е — платёж в терминальном статусе (`succeeded`/`failed`)
  повторно не обрабатывается: дубль сообщения из очереди (at-least-once
  доставка) не запускает обработку заново и не меняет уже установленный
  исход.

## Конфигурация (.env)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/payments
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
API_KEY=super-secret-key
```

## Решения и ограничения

- `relay` работает внутри процесса `consumer`, а не отдельным сервисом —
  ТЗ ограничивает состав compose четырьмя сервисами (postgres, rabbitmq,
  api, consumer). Логика вынесена в отдельный модуль (`worker/relay.py`) и
  при необходимости выносится в отдельный контейнер без изменения кода.
- `Decimal` передаётся в JSON строкой, чтобы не терять точность.
- Отказ платёжного шлюза (10% вероятность) — это нормальный бизнес-исход
  со статусом `failed`, по нему тоже отправляется webhook; в DLQ попадают
  только сообщения с неудавшейся доставкой или обработкой.
