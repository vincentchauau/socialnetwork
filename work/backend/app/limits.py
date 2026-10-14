"""Per-user sliding-window write limit (in memory, per process)."""

import time
from collections import deque
from typing import Callable

MAX_WRITES = 60
WINDOW_SECONDS = 60.0
PRUNE_AT = 1024


class UserRateLimiter:
    def __init__(
        self,
        max_events: int = MAX_WRITES,
        window: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_events
        self._window = window
        self._clock = clock
        self._events: dict[int, deque[float]] = {}

    def allow(self, user_id: int) -> bool:
        now = self._clock()
        if len(self._events) >= PRUNE_AT:
            self._prune(now)
        events = self._events.setdefault(user_id, deque())
        while events and events[0] <= now - self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(now)
        return True

    def _prune(self, now: float) -> None:
        for key in [k for k, ev in self._events.items() if not ev or ev[-1] <= now - self._window]:
            del self._events[key]
