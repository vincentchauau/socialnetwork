"""Per-user sliding-window limits shared by REST, WebSocket and chat (one budget per user, however many tabs)."""

import time
from collections.abc import Callable

from sn_shared.limits import PRUNE_AT, SlidingWindow

import logging
logger = logging.getLogger(__name__)

# kind -> (max events, window seconds)
RULES: dict[str, tuple[int, float]] = {
    "rest": (60, 10.0),  # any REST call
    "create": (6, 60.0),  # room creation
    "join": (15, 60.0),  # join attempts (guessing codes)
    "chat": (8, 10.0),  # chat messages, on top of the engine's 0.8 s spacing
    "ws": (20, 10.0),  # frames per user over all sockets
}


class UserLimits:
    """One sliding window per (kind, user); idle ones are pruned so the table stays bounded."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, rules: dict[str, tuple[int, float]] | None = None) -> None:
        try:
            self._clock = clock
            self._rules = rules or RULES
            self._limiters: dict[tuple[str, int], SlidingWindow] = {}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def allow(self, kind: str, user_id: int) -> bool:
        try:
            key = (kind, user_id)
            limiter = self._limiters.get(key)
            if limiter is None:
                if len(self._limiters) >= PRUNE_AT:
                    self.prune()
                max_events, window = self._rules[kind]
                limiter = self._limiters[key] = SlidingWindow(max_events, window, self._clock)
            return limiter.allow()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("allow failed")
            raise

    def prune(self) -> None:
        try:
            for key in [k for k, lim in self._limiters.items() if lim.idle()]:
                del self._limiters[key]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("prune failed")
            raise

    def size(self) -> int:
        try:
            return len(self._limiters)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("size failed")
            raise
