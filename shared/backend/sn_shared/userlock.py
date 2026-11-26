"""One operation at a time for each user (striped locks, so the memory stays small), for what the user keeps on disk."""

import threading

LOCK_STRIPES = 1024  # many, so two people are unlikely to share a lock and wait for each other
LOCK_TIMEOUT_SECONDS = 10.0
locks_userlock = [threading.Lock() for _ in range(LOCK_STRIPES)]


class Busy(RuntimeError):
    """Another operation of the same user holds the lock for too long (HTTP 429)."""


class user_lock:
    """Context manager: one operation at a time per user."""

    def __init__(self, user_id: int, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self.guard = locks_userlock[int(user_id) % LOCK_STRIPES]
        self._timeout = timeout

    def __enter__(self) -> None:
        if not self.guard.acquire(timeout=self._timeout):
            raise Busy("busy")

    def __exit__(self, *exc: object) -> None:
        self.guard.release()
