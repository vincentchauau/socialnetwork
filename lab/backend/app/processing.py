"""What the worker does with a message, independent of the broker libraries (so it is unit-tested with fakes)."""

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app import repo
from app.interfaces import LogRecord

log = logging.getLogger("lab.worker")

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
WORK_SECONDS = (0.3, 0.8)
FAIL_PREFIX = "[fail]"

OUTCOME_DONE = "done"
OUTCOME_DEAD = "dead"
OUTCOME_DROPPED = "dropped"

Sleep = Callable[[float], Awaitable[None]]


def _work_time() -> float:
    return random.uniform(*WORK_SECONDS)


class NotificationProcessor:
    """RabbitMQ side. `handle` returns "done"/"dropped" (ack) or "dead" (reject -> DLQ)."""

    def __init__(
        self,
        factory: sessionmaker,
        sleep: Sleep = asyncio.sleep,
        work_time: Callable[[], float] = _work_time,
        backoff_base: float = BACKOFF_BASE_SECONDS,
    ) -> None:
        self._factory = factory
        self._sleep = sleep
        self._work_time = work_time
        self._backoff_base = backoff_base

    async def _set(self, event_id: int, status: str, attempts: int) -> bool:
        return await asyncio.to_thread(repo.set_notification_status, self._factory, event_id, status, attempts)

    async def handle(self, body: bytes) -> str:
        event_id = _event_id(body)
        if event_id is None:
            log.warning("notification with an unreadable payload sent to the DLQ")
            return OUTCOME_DEAD
        title = await asyncio.to_thread(repo.get_notification_title, self._factory, event_id)
        if title is None:
            return OUTCOME_DROPPED  # the user cleared their events before the worker got here
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if not await self._set(event_id, repo.STATUS_PROCESSING, attempt):
                return OUTCOME_DROPPED
            await self._sleep(self._work_time())
            if not title.startswith(FAIL_PREFIX):
                await self._set(event_id, repo.STATUS_DONE, attempt)
                return OUTCOME_DONE
            if attempt == MAX_ATTEMPTS:
                break
            await self._set(event_id, repo.STATUS_RETRYING, attempt)
            await self._sleep(self._backoff_base * 2 ** (attempt - 1))
        await self._set(event_id, repo.STATUS_DEAD, MAX_ATTEMPTS)
        return OUTCOME_DEAD


def _event_id(body: bytes) -> int | None:
    try:
        value = json.loads(body)["id"]
    except (ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class LogWriter:
    """Kafka side: store one consumed message. The caller commits the offset after this returns."""

    def __init__(self, factory: sessionmaker) -> None:
        self._factory = factory

    async def handle(self, partition: int, offset: int, value: bytes, timestamp_ms: int = 0) -> bool:
        parsed = parse_log_value(value)
        if parsed is None:
            log.warning("log message at %s/%s skipped: unreadable payload", partition, offset)
            return False
        user_id, level, message = parsed
        created = (
            datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc) if timestamp_ms else datetime.now(timezone.utc)
        )
        return await asyncio.to_thread(
            repo.store_log, self._factory, user_id, level, message, partition, offset, created
        )


def parse_log_value(value: bytes) -> tuple[int, str, str] | None:
    try:
        data = json.loads(value)
        user_id, level, message = data["userId"], data["level"], data["message"]
    except (ValueError, KeyError, TypeError):
        return None
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        return None
    if level not in ("info", "warn", "error") or not isinstance(message, str) or len(message) > 200:
        return None
    return user_id, level, message


def replay_message(record: LogRecord) -> dict | None:
    parsed = parse_log_value(record.value)
    if parsed is None:
        return None
    _, level, message = parsed
    return {
        "offset": record.offset,
        "partition": record.partition,
        "level": level,
        "message": message,
        "timestamp": datetime.fromtimestamp(record.timestamp_ms / 1000, timezone.utc).isoformat(),
    }
