"""Small key/value layer for the counters and single-use markers that must be shared between replicas.

`MemoryKv` is per process (the default; dev and tests). `RedisKv` shares state through Redis: every key has a
TTL (memory stays bounded) and a `sn:` prefix. `ResilientKv` wraps Redis and falls back to a per-process
`MemoryKv` when Redis errors, so a Redis outage degrades the limits (per process) but never disables them
and never surfaces an error to the user.
"""

import math
import secrets
import threading
import time
from typing import Callable, Protocol

import redis
from redis.exceptions import RedisError

from app.audit import audit

DEFAULT_MAX_KEYS = 100_000
KEY_PREFIX = "sn:"
REDIS_TIMEOUT_SECONDS = 0.5
ERROR_LOG_INTERVAL_SECONDS = 60.0
STATUS_OK, STATUS_DEGRADED, STATUS_OFF = "ok", "degraded", "off"
TTL_SLACK_SECONDS = 1  # a Redis key outlives its window by a moment so a late trim never sees it expire first


class Kv(Protocol):
    def hit(self, key: str, window: float) -> int:
        """Record one event now; return how many events (including this one) fall in the last `window` seconds."""

    def hit_capped(self, key: str, window: float, limit: int) -> bool:
        """Record one event unless `limit` events are already inside the window. True when recorded."""

    def count(self, key: str, window: float) -> int: ...

    def clear(self, key: str) -> None: ...

    def set_if_absent(self, key: str, ttl: float) -> bool:
        """True for the first caller within `ttl` seconds (a single-use marker); False afterwards."""

    def tracked_keys(self, prefix: str = "") -> int: ...

    def probe(self) -> str:
        """`ok`, `degraded` or `off` (no shared store configured)."""


class MemoryKv:
    """Thread-safe in-process implementation. Bounded by `max_keys`: counters evict the oldest key,
    single-use markers fail closed (refuse) when full of live entries."""

    def __init__(self, max_keys: int = DEFAULT_MAX_KEYS, now: Callable[[], float] = time.monotonic) -> None:
        self._max_keys = max_keys
        self._now = now
        self._hits: dict[str, tuple[float, list[float]]] = {}  # key -> (window, timestamps)
        self._flags: dict[str, float] = {}  # key -> expiry
        self._lock = threading.Lock()

    def _recent(self, key: str, window: float) -> list[float]:
        cutoff = self._now() - window
        recent = [t for t in self._hits.get(key, (window, []))[1] if t > cutoff]
        if recent:
            self._hits[key] = (window, recent)
        else:
            self._hits.pop(key, None)
        return recent

    def _make_room(self) -> None:
        for key, (window, _) in list(self._hits.items()):
            self._recent(key, window)
        while len(self._hits) >= self._max_keys:
            oldest = min(self._hits, key=lambda k: self._hits[k][1][-1])
            del self._hits[oldest]

    def _append(self, key: str, window: float) -> int:
        if key not in self._hits and len(self._hits) >= self._max_keys:
            self._make_room()
        recent = self._recent(key, window)
        recent.append(self._now())
        self._hits[key] = (window, recent)
        return len(recent)

    def hit(self, key: str, window: float) -> int:
        with self._lock:
            return self._append(key, window)

    def hit_capped(self, key: str, window: float, limit: int) -> bool:
        with self._lock:
            if len(self._recent(key, window)) >= limit:
                return False
            self._append(key, window)
            return True

    def count(self, key: str, window: float) -> int:
        with self._lock:
            return len(self._recent(key, window))

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
            self._flags.pop(key, None)

    def set_if_absent(self, key: str, ttl: float) -> bool:
        with self._lock:
            now = self._now()
            if len(self._flags) >= self._max_keys:
                self._flags = {k: v for k, v in self._flags.items() if v > now}
                if len(self._flags) >= self._max_keys:
                    return False
            if self._flags.get(key, 0.0) > now:
                return False
            self._flags[key] = now + ttl
            return True

    def tracked_keys(self, prefix: str = "") -> int:
        with self._lock:
            return sum(1 for k in self._hits if k.startswith(prefix))

    def probe(self) -> str:
        return STATUS_OFF


class RedisKv:
    """Shared implementation. Sliding window = one sorted set per key (score = event time); each update is a
    MULTI/EXEC transaction, so concurrent replicas never lose a count."""

    def __init__(self, client: redis.Redis, now: Callable[[], float] = time.time) -> None:
        self._client = client
        self._now = now

    @classmethod
    def from_url(cls, url: str) -> "RedisKv":
        client = redis.Redis.from_url(
            url, socket_timeout=REDIS_TIMEOUT_SECONDS, socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            decode_responses=True,
        )  # fmt: skip
        return cls(client)

    @staticmethod
    def _name(key: str) -> str:
        return KEY_PREFIX + key

    def _add(self, key: str, window: float) -> tuple[int, str]:
        name, now = self._name(key), self._now()
        member = f"{now!r}:{secrets.token_hex(6)}"
        pipe = self._client.pipeline(transaction=True)
        pipe.zremrangebyscore(name, "-inf", now - window)
        pipe.zadd(name, {member: now})
        pipe.expire(name, max(1, math.ceil(window)) + TTL_SLACK_SECONDS)
        pipe.zcard(name)
        return int(pipe.execute()[-1]), member

    def hit(self, key: str, window: float) -> int:
        return self._add(key, window)[0]

    def hit_capped(self, key: str, window: float, limit: int) -> bool:
        total, member = self._add(key, window)
        if total <= limit:
            return True
        self._client.zrem(self._name(key), member)  # over the cap: this attempt does not count
        return False

    def count(self, key: str, window: float) -> int:
        name = self._name(key)
        pipe = self._client.pipeline(transaction=True)
        pipe.zremrangebyscore(name, "-inf", self._now() - window)
        pipe.zcard(name)
        return int(pipe.execute()[-1])

    def clear(self, key: str) -> None:
        self._client.delete(self._name(key))

    def set_if_absent(self, key: str, ttl: float) -> bool:
        return bool(self._client.set(self._name(key), "1", nx=True, ex=max(1, math.ceil(ttl))))

    def tracked_keys(self, prefix: str = "") -> int:
        return sum(1 for _ in self._client.scan_iter(match=self._name(prefix) + "*"))

    def probe(self) -> str:
        self._client.ping()
        return STATUS_OK


class ResilientKv:
    """Primary store with a per-process fallback: any Redis failure serves that call from memory."""

    def __init__(
        self, primary: Kv, fallback: MemoryKv | None = None, now: Callable[[], float] = time.monotonic
    ) -> None:
        self._primary = primary
        self._fallback = fallback or MemoryKv()
        self._now = now
        self._degraded = False
        self._last_logged: float | None = None
        self._log_lock = threading.Lock()

    def _failed(self, exc: Exception) -> None:
        self._degraded = True
        with self._log_lock:
            now = self._now()
            if self._last_logged is not None and now - self._last_logged < ERROR_LOG_INTERVAL_SECONDS:
                return
            self._last_logged = now
        audit.error("redis unavailable (%s): limits are per process until it recovers", type(exc).__name__)

    def _call(self, method: str, *args):
        try:
            result = getattr(self._primary, method)(*args)
        except (RedisError, OSError) as exc:
            self._failed(exc)
            return getattr(self._fallback, method)(*args)
        self._degraded = False
        return result

    def hit(self, key: str, window: float) -> int:
        return self._call("hit", key, window)

    def hit_capped(self, key: str, window: float, limit: int) -> bool:
        return self._call("hit_capped", key, window, limit)

    def count(self, key: str, window: float) -> int:
        return self._call("count", key, window)

    def clear(self, key: str) -> None:
        self._fallback.clear(key)  # also drop what a past outage left in memory
        self._call("clear", key)

    def set_if_absent(self, key: str, ttl: float) -> bool:
        return self._call("set_if_absent", key, ttl)

    def tracked_keys(self, prefix: str = "") -> int:
        return self._call("tracked_keys", prefix)

    def probe(self) -> str:
        try:
            self._primary.probe()
        except (RedisError, OSError) as exc:
            self._failed(exc)
            return STATUS_DEGRADED
        self._degraded = False
        return STATUS_OK

    @property
    def degraded(self) -> bool:
        return self._degraded


def make_kv(redis_url: str) -> Kv:
    """MemoryKv when `redis_url` is empty; otherwise Redis with an in-process fallback (never raises)."""
    if not redis_url:
        return MemoryKv()
    kv = ResilientKv(RedisKv.from_url(redis_url))
    if kv.probe() != STATUS_OK:
        audit.error("redis is not reachable at startup: continuing with per-process limits")
    return kv
