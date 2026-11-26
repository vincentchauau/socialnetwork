import time
from typing import Callable

from api.center.kv import DEFAULT_MAX_KEYS, Kv, MemoryKv

import logging
logger = logging.getLogger(__name__)


def pair_key(*parts: str) -> str:
    """One throttle key from several parts, injective whatever the parts contain (length-prefixed)."""
    try:
        return "|".join(f"{len(part)}:{part}" for part in parts)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("pair_key failed")
        raise


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
        try:
            if kv is not None and not name:
                raise ValueError("a throttle on a shared Kv needs a name")
            self._max_attempts = max_attempts
            self._window = window_seconds
            self._prefix = f"throttle:{name}:"
            self._kv: Kv = kv if kv is not None else MemoryKv(max_keys=max_keys, now=now)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def key_throttle(self, key: str) -> str:
        try:
            return self._prefix + key
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("key_throttle failed")
            raise

    def is_blocked(self, key: str) -> bool:
        try:
            return self._kv.count(self.key_throttle(key), self._window) >= self._max_attempts
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("is_blocked failed")
            raise

    def count(self, key: str) -> int:
        try:
            return self._kv.count(self.key_throttle(key), self._window)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("count failed")
            raise

    def record(self, key: str) -> None:
        try:
            self._kv.hit(self.key_throttle(key), self._window)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("record failed")
            raise

    def check_and_record(self, key: str) -> bool:
        """Atomic is_blocked + record: True (and counted) when allowed, False (not counted) when blocked."""
        try:
            return self._kv.hit_capped(self.key_throttle(key), self._window, self._max_attempts)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("check_and_record failed")
            raise

    def reset(self, key: str) -> None:
        try:
            self._kv.clear(self.key_throttle(key))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("reset failed")
            raise

    def tracked_keys(self) -> int:
        try:
            return self._kv.tracked_keys(self._prefix)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("tracked_keys failed")
            raise
