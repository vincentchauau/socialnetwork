"""Where the per-user data lives (WORK_DATA_DIR) and the per-user locks.

    <WORK_DATA_DIR>/files/<user_id>/...        file sandbox
    <WORK_DATA_DIR>/incoming/                  upload temp files (same filesystem: atomic rename)
    <WORK_DATA_DIR>/db/<user_id>.sqlite3       SQLite database (+ transient journal files)
"""

import os
import shutil
import threading
from pathlib import Path

DEFAULT_DATA_DIR = "/data/work"
LOCK_STRIPES = 64
LOCK_TIMEOUT_SECONDS = 10.0
DB_SUFFIXES = ("", "-journal", "-wal", "-shm")
_locks = [threading.Lock() for _ in range(LOCK_STRIPES)]


class Busy(RuntimeError):
    """Another operation of the same user holds the lock for too long (HTTP 429)."""


def data_dir() -> Path:
    return Path(os.environ.get("WORK_DATA_DIR", DEFAULT_DATA_DIR))


def files_root(user_id: int) -> Path:
    return data_dir() / "files" / str(int(user_id))


def incoming_dir() -> Path:
    return data_dir() / "incoming"


def db_path(user_id: int) -> Path:
    return data_dir() / "db" / f"{int(user_id)}.sqlite3"


class user_lock:
    """Context manager: one operation at a time per user (striped, so memory stays bounded)."""

    def __init__(self, user_id: int, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self._lock = _locks[int(user_id) % LOCK_STRIPES]
        self._timeout = timeout

    def __enter__(self) -> None:
        if not self._lock.acquire(timeout=self._timeout):
            raise Busy("busy")

    def __exit__(self, *exc: object) -> None:
        self._lock.release()


def erase_user(user_id: int) -> None:
    """Remove the user's file tree and SQLite file; idempotent, never follows symlinks."""
    if user_id <= 0:
        return
    with user_lock(user_id):
        root = files_root(user_id)
        if root.is_symlink():
            root.unlink(missing_ok=True)
        elif root.exists():
            shutil.rmtree(root, ignore_errors=True)
        base = db_path(user_id)
        for suffix in DB_SUFFIXES:
            Path(str(base) + suffix).unlink(missing_ok=True)
