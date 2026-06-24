payments-service

Сервис асинхронной обработки платежей. Принимает запрос на оплату, прогоняет его
через эмуляцию платёжного шлюза и отправляет результат на webhook.

Стек

FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), PostgreSQL, RabbitMQ (FastStream),
Alembic, Docker.

Как работает

API при создании платежа кладёт его в БД и в той же транзакции пишет событие в
таблицу outbox. Отдельная корутина (relay) вычитывает outbox и публикует
события в очередь payments.new. За счёт этого событие не теряется, даже если в
момент создания RabbitMQ недоступен — это outbox pattern.

Consumer читает payments.new, эмулирует обработку (2–5 сек, 90% успех / 10%
отказ), обновляет статус платежа и шлёт webhook. Доставку webhook ретраит 3 раза
с экспоненциальной задержкой. Если так и не доставили — сообщение уходит в DLQ
(payments.dlq).

Идемпотентность сделана в двух местах: на создании платежа по заголовку
Idempotency-Key (уникальный индекс, повторный запрос возвращает уже созданный
платёж), и в consumer'е — платёж в финальном статусе повторно не обрабатывается.

Запуск

cp .env.example .env
docker compose up --build

Поднимаются postgres, rabbitmq, api, consumer. Миграции накатываются автоматически
при старте api.


API — http://localhost:8000
Swagger — http://localhost:8000/docs
RabbitMQ — http://localhost:15672 (guest / guest)


API

Во всех запросах нужен заголовок X-API-Key.

Создать платёж:

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

Ответ 202:

{
  "payment_id": "b3f1c2d4-...",
  "status": "pending",
  "created_at": "2026-06-24T10:15:00Z"
}

Получить платёж:

curl http://localhost:8000/api/v1/payments/<payment_id> \
  -H "X-API-Key: super-secret-key"

На webhook_url приходит POST с результатом:

{
  "payment_id": "b3f1c2d4-...",
  "status": "succeeded",
  "amount": "100.50",
  "currency": "RUB",
  "processed_at": "2026-06-24T10:15:04Z"
}

Очереди


payments.new — основная очередь, объявлена с dead-letter exchange.
payments.dlx / payments.dlq — обменник и очередь для сообщений, которые не
удалось обработать после ретраев.


Конфиг (.env)

API_KEY=super-secret-key
POSTGRES_DSN=postgresql+asyncpg://postgres:postgres@postgres:5432/payments
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
WEBHOOK_MAX_RETRIES=3
OUTBOX_POLL_INTERVAL=1.0

Заметки по реализации


relay крутится внутри процесса consumer'а, чтобы не плодить контейнеры сверх
тех, что в задании. При необходимости легко вынести отдельным сервисом.
decimal в JSON передаётся строкой, чтобы не терять точность на float.
отказ шлюза (10%) — это нормальный бизнес-результат со статусом failed, по
нему тоже уходит webhook; в DLQ попадают только сообщения с неудавшейся
доставкой/обработкой.
