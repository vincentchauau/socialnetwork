"""Per-user sliding-window limits shared by REST, WebSocket and chat (one budget per user, however many tabs)."""

import time
from collections import deque
from typing import Callable

# kind -> (max events, window seconds)
RULES: dict[str, tuple[int, float]] = {
    "rest": (60, 10.0),  # any REST call
    "create": (6, 60.0),  # room creation
    "join": (15, 60.0),  # join attempts (guessing codes)
    "chat": (8, 10.0),  # chat messages, on top of the engine's 0.8 s spacing
    "ws": (20, 10.0),  # frames per user over all sockets
}


class MessageRateLimiter:
    """Sliding-window limit on how many events one key may produce."""

    def __init__(self, max_events: int, window_seconds: float, now: Callable[[], float] = time.monotonic) -> None:
        self._max_events = max_events
        self._window = window_seconds
        self._now = now
        self._events: deque[float] = deque()

    def idle(self) -> bool:
        current = self._now()
        return not self._events or self._events[-1] <= current - self._window

    def allow(self) -> bool:
        current = self._now()
        while self._events and self._events[0] <= current - self._window:
            self._events.popleft()
        if len(self._events) >= self._max_events:
            return False
        self._events.append(current)
        return True


class UserLimits:
    """One limiter per (kind, user); idle ones are pruned so the table stays bounded."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, rules: dict[str, tuple[int, float]] | None = None) -> None:
        self._clock = clock
        self._rules = rules or RULES
        self._limiters: dict[tuple[str, int], MessageRateLimiter] = {}

    def allow(self, kind: str, user_id: int) -> bool:
        key = (kind, user_id)
        limiter = self._limiters.get(key)
        if limiter is None:
            if len(self._limiters) >= 1024:
                self.prune()
            max_events, window = self._rules[kind]
            limiter = self._limiters[key] = MessageRateLimiter(max_events, window, self._clock)
        return limiter.allow()

    def prune(self) -> None:
        for key in [k for k, lim in self._limiters.items() if lim.idle()]:
            del self._limiters[key]

    def size(self) -> int:
        return len(self._limiters)
