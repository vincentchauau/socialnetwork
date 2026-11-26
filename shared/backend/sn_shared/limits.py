"""The sliding-window limit of the platform: at most N events in the last W seconds, in memory per process.

`SlidingWindow` is the one counter. `UserRateLimiter` keeps one per user (the writes and reads of the REST routes), and the
dependencies `writer` and `reader` apply the limit of the app to the signed-in user. Apps with other keys (a kind of event,
a connection) use `SlidingWindow` directly.
"""

import time
from collections import deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)

MAX_WRITES = 60
WINDOW_SECONDS = 60.0
PRUNE_AT = 1024  # keys remembered before the ones with nothing recent are forgotten
TOO_FAST = "Bạn thao tác quá nhanh, hãy thử lại sau"


class SlidingWindow:
    """At most `max_events` in the last `window_seconds` (an event is allowed only when the window has room)."""

    def __init__(self, max_events: int, window_seconds: float, now: Callable[[], float] = time.monotonic) -> None:
        try:
            self._max_events = max_events
            self._window = window_seconds
            self.now_totp = now
            self._events: deque[float] = deque()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def idle(self) -> bool:
        try:
            current = self.now_totp()
            return not self._events or self._events[-1] <= current - self._window
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("idle failed")
            raise

    def allow(self) -> bool:
        try:
            current = self.now_totp()
            while self._events and self._events[0] <= current - self._window:
                self._events.popleft()
            if len(self._events) >= self._max_events:
                return False
            self._events.append(current)
            return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("allow failed")
            raise


class UserRateLimiter:
    """One sliding window per user id; idle ones are pruned so the table stays bounded."""

    def __init__(self, max_events: int = MAX_WRITES, window: float = WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        try:
            self._max = max_events
            self._window = window
            self._clock = clock
            self._events: dict[int, SlidingWindow] = {}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def allow(self, user_id: int) -> bool:
        try:
            window = self._events.get(user_id)
            if window is None:
                if len(self._events) >= PRUNE_AT:
                    self.prune()
                window = self._events[user_id] = SlidingWindow(self._max, self._window, self._clock)
            return window.allow()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("allow failed")
            raise

    def prune(self) -> None:
        try:
            for key in [k for k, w in self._events.items() if w.idle()]:
                del self._events[key]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("prune failed")
            raise


def writer(request: Request, user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Authenticated user within the write limit of the app (`app.state.limiter`, 60 a minute)."""
    try:
        if not request.app.state.limiter.allow(user.user_id):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_FAST)
        return user
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("writer failed")
        raise


def reader(request: Request, user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Authenticated user within the (more generous) read limit of the app (`app.state.read_limiter`)."""
    try:
        if not request.app.state.read_limiter.allow(user.user_id):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_FAST)
        return user
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("reader failed")
        raise
