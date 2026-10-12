import threading
import time
from typing import Callable

DEFAULT_MAX_KEYS = 10_000


class AttemptThrottle:
    """Blocks a key (an IP, an IP+username pair...) after too many recent attempts.

    In-memory and per-process: enough to slow online guessing against a single
    instance. Move the counters to Redis before running several replicas.
    The number of tracked keys is capped so random keys cannot exhaust memory.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 300.0,
        max_keys: int = DEFAULT_MAX_KEYS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._max_keys = max_keys
        self._now = now
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = self._now() - self._window
        recent = [t for t in self._attempts.get(key, []) if t > cutoff]
        if recent:
            self._attempts[key] = recent
        else:
            self._attempts.pop(key, None)
        return recent

    def _make_room(self) -> None:
        for key in list(self._attempts):
            self._recent(key)
        while len(self._attempts) >= self._max_keys:
            oldest = min(self._attempts, key=lambda k: self._attempts[k][-1])
            del self._attempts[oldest]

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._max_attempts

    def record(self, key: str) -> None:
        with self._lock:
            if key not in self._attempts and len(self._attempts) >= self._max_keys:
                self._make_room()
            self._recent(key)
            self._attempts.setdefault(key, []).append(self._now())

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._attempts)
