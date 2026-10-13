"""Kafka (aiokafka): producer for POST /logs, group consumer for the worker, group-less replay."""

import asyncio
import os
import time
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from app.interfaces import LOG_GROUP, LOG_TOPIC, LogRecord, Unavailable

CONNECT_TIMEOUT_SECONDS = 2.0
SEND_TIMEOUT_SECONDS = 3.0
REPLAY_TIMEOUT_SECONDS = 3.0
REPLAY_MAX_SCAN = 5000


def bootstrap() -> str:
    return os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")


async def ensure_topic() -> None:
    """auto.create.topics.enable is off: create `lab.logs` (1 partition) when it is missing."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap(), request_timeout_ms=3000)
    await admin.start()
    try:
        await admin.create_topics([NewTopic(LOG_TOPIC, num_partitions=1, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass
    finally:
        await admin.close()


async def _quiet_stop(client) -> None:
    try:
        await client.stop()
    except BaseException:
        pass


class KafkaLogBus:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> AIOKafkaProducer:
        async with self._lock:
            if self._producer is not None:
                return self._producer
            producer = AIOKafkaProducer(bootstrap_servers=bootstrap(), acks="all", request_timeout_ms=3000)
            try:
                await asyncio.wait_for(producer.start(), CONNECT_TIMEOUT_SECONDS)
                await asyncio.wait_for(ensure_topic(), CONNECT_TIMEOUT_SECONDS + 1)
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
            meta = await asyncio.wait_for(
                producer.send_and_wait(LOG_TOPIC, value, key=key.encode()), SEND_TIMEOUT_SECONDS
            )
        except Exception as exc:
            await self._reset()
            raise Unavailable("kafka") from exc
        return meta.partition, meta.offset

    async def replay(self, key: str, limit: int) -> list[LogRecord]:
        deadline = time.monotonic() + REPLAY_TIMEOUT_SECONDS
        consumer = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
        try:
            await asyncio.wait_for(consumer.start(), CONNECT_TIMEOUT_SECONDS)
            partition = TopicPartition(LOG_TOPIC, 0)
            consumer.assign([partition])
            await consumer.seek_to_beginning(partition)
            end = (await consumer.end_offsets([partition]))[partition]
            found: list[LogRecord] = []
            scanned = 0
            while len(found) < limit and scanned < REPLAY_MAX_SCAN and await consumer.position(partition) < end:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                batch = await consumer.getmany(partition, timeout_ms=int(min(remaining, 0.5) * 1000), max_records=500)
                for record in batch.get(partition, []):
                    scanned += 1
                    if record.key == key.encode() and len(found) < limit:
                        found.append(LogRecord(key, record.partition, record.offset, record.value, record.timestamp))
            return found
        except Exception as exc:
            raise Unavailable("kafka") from exc
        finally:
            await _quiet_stop(consumer)

    async def ping(self) -> bool:
        try:
            producer = await self._ensure()
            await asyncio.wait_for(producer.client.force_metadata_update(), 1.0)
        except Exception:
            await self._reset()
            return False
        return True

    async def close(self) -> None:
        await self._reset()


LogHandler = Callable[[int, int, bytes, int], Awaitable[None]]


async def consume_logs(handler: LogHandler, stop: asyncio.Event) -> None:
    """Group consumer: auto commit off, the offset is committed after `handler` (the DB write) returned."""
    await ensure_topic()
    consumer = AIOKafkaConsumer(
        LOG_TOPIC,
        bootstrap_servers=bootstrap(),
        group_id=LOG_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        while not stop.is_set():
            batch = await consumer.getmany(timeout_ms=1000, max_records=50)
            for partition, records in batch.items():
                for record in records:
                    await handler(record.partition, record.offset, record.value, record.timestamp)
                    await consumer.commit({partition: record.offset + 1})
    finally:
        await _quiet_stop(consumer)
