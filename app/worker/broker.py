from faststream.rabbit import RabbitBroker, RabbitQueue, RabbitExchange, ExchangeType
from app.core.config import settings

broker = RabbitBroker(settings.rabbitmq_url)

dead_letter_exchange = RabbitExchange("payments.dlx", type=ExchangeType.FANOUT, durable=True)

payments_new = RabbitQueue("payments.new", durable=True, arguments={"x-dead-letter-exchange": "payments.dlx"}, )

payments_dlq = RabbitQueue("payments.dlq", durable=True)


async def declare_dlq() -> None:
    exchange = await broker.declare_exchange(dead_letter_exchange)
    queue = await broker.declare_queue(payments_dlq)
    await queue.bind(exchange)
