import time
from typing import Callable

from api.center.kv import DEFAULT_MAX_KEYS, Kv, MemoryKv


def pair_key(*parts: str) -> str:
    """One throttle key from several parts, injective whatever the parts contain (length-prefixed)."""
    return "|".join(f"{len(part)}:{part}" for part in parts)


class AttemptThrottle:
    """Blocks a key (an IP, an IP+username pair...) after too many recent attempts.

    The counters live in a `Kv`: per process by default (enough to slow online guessing against one
    instance), shared between replicas when the app is given a Redis-backed one. Throttles sharing a `Kv`
    need distinct `name`s, which namespace their keys.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 300.0,
        max_keys: int = DEFAULT_MAX_KEYS,
        now: Callable[[], float] = time.monotonic,
        *,
        name: str = "",
        kv: Kv | None = None,
    ) -> None:
        if kv is not None and not name:
            raise ValueError("a throttle on a shared Kv needs a name")
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._prefix = f"throttle:{name}:"
        self._kv: Kv = kv if kv is not None else MemoryKv(max_keys=max_keys, now=now)

    def _key(self, key: str) -> str:
        return self._prefix + key

    def is_blocked(self, key: str) -> bool:
        return self._kv.count(self._key(key), self._window) >= self._max_attempts

    def count(self, key: str) -> int:
        return self._kv.count(self._key(key), self._window)

    def record(self, key: str) -> None:
        self._kv.hit(self._key(key), self._window)

    def check_and_record(self, key: str) -> bool:
        """Atomic is_blocked + record: True (and counted) when allowed, False (not counted) when blocked."""
        return self._kv.hit_capped(self._key(key), self._window, self._max_attempts)

    def reset(self, key: str) -> None:
        self._kv.clear(self._key(key))

    def tracked_keys(self) -> int:
        return self._kv.tracked_keys(self._prefix)
