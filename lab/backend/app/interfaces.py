"""The four things the backend talks to, as small async interfaces.

Real implementations live in app/adapters; unit tests inject in-memory fakes. Every adapter maps ALL of its
library errors to `Unavailable`, so the routes never see a library exception.
"""

from dataclasses import dataclass
from typing import Protocol

NOTIFICATION_QUEUE = "lab.notifications"
NOTIFICATION_DLX = "lab.notifications.dlx"
NOTIFICATION_DLQ = "lab.notifications.dlq"
NOTIFICATION_MAX_LENGTH = 1000
LOG_TOPIC = "lab.logs"
LOG_GROUP = "lab-log-writer"
USER_CACHE_PREFIX = "lab:user:"
USER_CACHE_TTL_SECONDS = 300
PROBE_TIMEOUT_SECONDS = 1.0


class Unavailable(Exception):
    """A backing service (Redis, gRPC, RabbitMQ, Kafka) did not answer."""


@dataclass(frozen=True)
class LogRecord:
    key: str
    partition: int
    offset: int
    value: bytes
    timestamp_ms: int


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class UserDirectory(Protocol):
    async def get_user(self, user_id: str) -> str:
        """The display name; raises Unavailable when the gRPC server is unreachable."""
        ...

    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class NotificationQueue(Protocol):
    async def publish(self, payload: bytes) -> None: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class LogBus(Protocol):
    async def publish(self, key: str, value: bytes) -> tuple[int, int]:
        """(partition, offset) of the stored message."""
        ...

    async def replay(self, key: str, limit: int) -> list[LogRecord]:
        """Up to `limit` messages with this key, read from the beginning by a fresh group-less consumer."""
        ...

    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


@dataclass
class Services:
    cache: Cache
    users: UserDirectory
    queue: NotificationQueue
    logs: LogBus
