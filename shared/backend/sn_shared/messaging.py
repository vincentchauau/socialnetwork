"""The messaging every module of the backend may use, all optional: a module asks for a broker only when it needs one, and a broker that is
not configured or not running is `Unavailable` (the caller answers 503 or goes on without it), never a crash at start-up.

- `WorkQueue` (RabbitMQ): a durable queue with a dead-letter queue; `publish`, and `consume` for a worker.
- `EventLog` (Kafka): an append-only topic; `publish`, and `replay` of the records of one key.

Settings come from the environment: RABBITMQ_HOST/PORT/USER/PASSWORD and KAFKA_BOOTSTRAP; a gRPC target is given by the caller.
Plain `connect`, not `connect_robust`: a failed first connect of the robust variant keeps retrying in the background forever. A lost
connection is noticed (`is_closed`) and re-established by the next call.
"""

import asyncio
import contextlib
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

CONNECT_TIMEOUT_SECONDS = 1.5
PUBLISH_TIMEOUT_SECONDS = 2.0
SEND_TIMEOUT_SECONDS = 3.0
REPLAY_TIMEOUT_SECONDS = 3.0
REPLAY_MAX_SCAN = 5000
PREFETCH = 5
DEAD_ROUTING_KEY = "dead"
DEAD = "dead"  # what a handler returns to send the message to the dead-letter queue


class Unavailable(Exception):
    """A broker is not configured, not reachable, or did not answer in time."""

    def __init__(self, what: str) -> None:
        super().__init__(f"{what} is unavailable")
        self.what = what


# ---- RabbitMQ ----------------------------------------------------------------------------------------------------------------------


def rabbitmq_settings() -> dict:
    return {
        "host": os.environ.get("RABBITMQ_HOST", "rabbitmq"),
        "port": int(os.environ.get("RABBITMQ_PORT", "5672")),
        "login": os.environ.get("RABBITMQ_USER", "guest"),
        "password": os.environ.get("RABBITMQ_PASSWORD", ""),
    }


@dataclass(frozen=True)
class QueueSpec:
    """A queue and its dead-letter queue. Publisher and consumer must declare it with IDENTICAL arguments (RabbitMQ refuses a redeclare that differs)."""

    name: str
    max_length: int = 1000

    @property
    def dead_exchange(self) -> str:
        return f"{self.name}.dlx"

    @property
    def dead_queue(self) -> str:
        return f"{self.name}.dlq"


async def _declare(channel, spec: QueueSpec):
    import aio_pika

    dlx = await channel.declare_exchange(spec.dead_exchange, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(spec.dead_queue, durable=True)
    await dlq.bind(dlx, routing_key=DEAD_ROUTING_KEY)
    return await channel.declare_queue(
        spec.name,
        durable=True,
        arguments={"x-max-length": spec.max_length, "x-dead-letter-exchange": spec.dead_exchange, "x-dead-letter-routing-key": DEAD_ROUTING_KEY},
    )


class WorkQueue:
    """The publishing side of one queue. Make one per process and `close` it at shutdown."""

    def __init__(self, spec: QueueSpec) -> None:
        self.spec = spec
        self._connection = None
        self._channel = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        import aio_pika

        async with self._lock:
            if self._channel is not None and not self._channel.is_closed:
                return self._channel
            await self._drop()
            try:
                self._connection = await aio_pika.connect(timeout=CONNECT_TIMEOUT_SECONDS, **rabbitmq_settings())
                self._channel = await self._connection.channel(publisher_confirms=True)
                await _declare(self._channel, self.spec)
            except BaseException:
                await self._drop()
                raise
            return self._channel

    async def _drop(self) -> None:
        connection, self._connection, self._channel = self._connection, None, None
        if connection is not None:
            with contextlib.suppress(Exception):
                await connection.close()

    async def publish(self, payload: bytes, content_type: str = "application/json") -> None:
        import aio_pika

        try:
            channel = await asyncio.wait_for(self._ensure(), CONNECT_TIMEOUT_SECONDS + 1)
            await channel.default_exchange.publish(
                aio_pika.Message(payload, content_type=content_type, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key=self.spec.name,
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


async def consume(spec: QueueSpec, handler: Handler, stop: asyncio.Event) -> None:
    """Consume until `stop` is set; raises if the broker cannot be reached (the caller reconnects).

    `handler(body)` returns `DEAD` to reject to the dead-letter queue, anything else to ack; an exception puts the message back.
    """
    import aio_pika

    connection = await aio_pika.connect(timeout=CONNECT_TIMEOUT_SECONDS, **rabbitmq_settings())
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH)
        queue = await _declare(channel, spec)

        async def on_message(message) -> None:
            try:
                outcome = await handler(message.body)
            except Exception:
                await message.nack(requeue=True)
                return
            if outcome == DEAD:
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


# ---- Kafka -------------------------------------------------------------------------------------------------------------------------


def kafka_bootstrap() -> str:
    return os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")


async def _quiet_stop(client) -> None:
    with contextlib.suppress(BaseException):
        await client.stop()


async def ensure_topic(topic: str) -> None:
    """auto.create.topics.enable is off in our broker: create the topic (1 partition) when it is missing."""
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic
    from aiokafka.errors import TopicAlreadyExistsError

    admin = AIOKafkaAdminClient(bootstrap_servers=kafka_bootstrap(), request_timeout_ms=3000)
    await admin.start()
    try:
        await admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass
    finally:
        await admin.close()


@dataclass(frozen=True)
class LogRecord:
    key: str
    value: bytes
    partition: int
    offset: int


class EventLog:
    """One Kafka topic: `publish` appends, `replay` reads the records of a key from the start (no consumer group, nothing is committed)."""

    def __init__(self, topic: str) -> None:
        self.topic = topic
        self._producer = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        from aiokafka import AIOKafkaProducer

        async with self._lock:
            if self._producer is not None:
                return self._producer
            producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap(), acks="all", request_timeout_ms=3000)
            try:
                await asyncio.wait_for(producer.start(), CONNECT_TIMEOUT_SECONDS + 0.5)
                await asyncio.wait_for(ensure_topic(self.topic), CONNECT_TIMEOUT_SECONDS + 1)
            except BaseException:
                await _quiet_stop(producer)
                raise
            self._producer = producer
            return producer

    async def _reset(self) -> None:
        producer, self._producer = self._producer, None
        if producer is not None:
            await _quiet_stop(producer)

    async def publish(self, key: str, value: bytes) -> tuple[int, int]:
        try:
            producer = await self._ensure()
            meta = await asyncio.wait_for(producer.send_and_wait(self.topic, value, key=key.encode()), SEND_TIMEOUT_SECONDS)
        except Exception as exc:
            await self._reset()
            raise Unavailable("kafka") from exc
        return meta.partition, meta.offset

    async def replay(self, key: str, limit: int) -> list[LogRecord]:
        from aiokafka import AIOKafkaConsumer, TopicPartition

        deadline = time.monotonic() + REPLAY_TIMEOUT_SECONDS
        consumer = AIOKafkaConsumer(bootstrap_servers=kafka_bootstrap(), group_id=None, enable_auto_commit=False)
        try:
            await asyncio.wait_for(consumer.start(), CONNECT_TIMEOUT_SECONDS + 0.5)
            partition = TopicPartition(self.topic, 0)
            consumer.assign([partition])
            await consumer.seek_to_beginning(partition)
            end = (await consumer.end_offsets([partition]))[partition]
            found: list[LogRecord] = []
            scanned = 0
            wanted = key.encode()
            while len(found) < limit and scanned < REPLAY_MAX_SCAN and await consumer.position(partition) < end:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                batch = await asyncio.wait_for(consumer.getmany(partition, timeout_ms=500, max_records=200), remaining + 0.5)
                for record in batch.get(partition, []):
                    scanned += 1
                    if record.key == wanted and len(found) < limit:
                        found.append(LogRecord(key=key, value=record.value, partition=record.partition, offset=record.offset))
            return found
        except Exception as exc:
            raise Unavailable("kafka") from exc
        finally:
            await _quiet_stop(consumer)

    async def close(self) -> None:
        await self._reset()
