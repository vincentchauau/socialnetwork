"""RabbitMQ (aio-pika): a durable work queue with a dead-letter queue.

Plain `connect`, not `connect_robust`: a failed first connect of the robust variant keeps retrying in the
background forever. Here a lost connection is noticed (`is_closed`) and re-established by the next call / by
the worker supervisor.

Publisher and consumer declare the queue with IDENTICAL arguments (RabbitMQ refuses a redeclare that differs).
"""

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractConnection, AbstractIncomingMessage

from app.interfaces import (
    NOTIFICATION_DLQ,
    NOTIFICATION_DLX,
    NOTIFICATION_MAX_LENGTH,
    NOTIFICATION_QUEUE,
    Unavailable,
)

CONNECT_TIMEOUT_SECONDS = 1.5
PUBLISH_TIMEOUT_SECONDS = 2.0
PREFETCH = 5
DEAD_ROUTING_KEY = "dead"


def connection_settings() -> dict:
    return {
        "host": os.environ.get("RABBITMQ_HOST", "rabbitmq"),
        "port": int(os.environ.get("RABBITMQ_PORT", "5672")),
        "login": os.environ.get("RABBITMQ_USER", "lab"),
        "password": os.environ.get("RABBITMQ_PASSWORD", ""),
    }


async def declare_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractQueue:
    dlx = await channel.declare_exchange(NOTIFICATION_DLX, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(NOTIFICATION_DLQ, durable=True)
    await dlq.bind(dlx, routing_key=DEAD_ROUTING_KEY)
    return await channel.declare_queue(
        NOTIFICATION_QUEUE,
        durable=True,
        arguments={
            "x-max-length": NOTIFICATION_MAX_LENGTH,
            "x-dead-letter-exchange": NOTIFICATION_DLX,
            "x-dead-letter-routing-key": DEAD_ROUTING_KEY,
        },
    )


class AmqpNotificationQueue:
    def __init__(self) -> None:
        self._connection: AbstractConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> aio_pika.abc.AbstractChannel:
        async with self._lock:
            if self._channel is not None and not self._channel.is_closed:
                return self._channel
            await self._drop()
            try:
                self._connection = await aio_pika.connect(timeout=CONNECT_TIMEOUT_SECONDS, **connection_settings())
                self._channel = await self._connection.channel(publisher_confirms=True)
                await declare_topology(self._channel)
            except BaseException:
                await self._drop()
                raise
            return self._channel

    async def _drop(self) -> None:
        connection, self._connection, self._channel = self._connection, None, None
        if connection is not None:
            try:
                await connection.close()
            except Exception:
                pass

    async def publish(self, payload: bytes) -> None:
        try:
            channel = await asyncio.wait_for(self._ensure(), CONNECT_TIMEOUT_SECONDS + 1)
            await channel.default_exchange.publish(
                aio_pika.Message(payload, content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key=NOTIFICATION_QUEUE,
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise Unavailable("rabbitmq") from exc

    async def ping(self) -> bool:
        try:
            await asyncio.wait_for(self._ensure(), CONNECT_TIMEOUT_SECONDS)
        except Exception:
            return False
        return True

    async def close(self) -> None:
        await self._drop()


Handler = Callable[[bytes], Awaitable[str]]


async def consume_notifications(handler: Handler, stop: asyncio.Event) -> None:
    """Consume until `stop` is set; raises if the broker cannot be reached (the caller reconnects).

    `handler(body)` returns "dead" to reject to the DLQ, anything else to ack.
    """
    connection = await aio_pika.connect(timeout=CONNECT_TIMEOUT_SECONDS, **connection_settings())
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH)
        queue = await declare_topology(channel)

        async def on_message(message: AbstractIncomingMessage) -> None:
            try:
                outcome = await handler(message.body)
            except Exception:
                await message.nack(requeue=True)
                return
            if outcome == "dead":
                await message.reject(requeue=False)
            else:
                await message.ack()

        await queue.consume(on_message)
        while not stop.is_set():
            if connection.is_closed or channel.is_closed:
                raise ConnectionError("rabbitmq connection lost")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), 1.0)
    finally:
        await connection.close()
