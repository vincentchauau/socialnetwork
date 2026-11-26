"""The links that give one file of a person to anybody who has them, without a sign-in (the file stays where it is; the link only points at it).

    <FILE_DATA_DIR>/shares/<token>.json   {"user_id", "path", "createdAt", "expiresAt"}

The token is random (128 bits) and is the only thing that opens the link. A person takes it back by deleting it; it also goes when its time is up, when
the file is gone, and with the account. One file has one link: a new one replaces the old one.
"""

import json
import re
import secrets
import time
from pathlib import Path

from api.file import store

import logging
logger = logging.getLogger(__name__)

TOKEN_BYTES = 16
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_SHARES_PER_USER = 50
MAX_DAYS = 365
PAGE_PATH = "/file/s/"


def shares_dir() -> Path:
    try:
        return store.data_dir() / "shares"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("shares_dir failed")
        raise


def read_shares(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return record if isinstance(record, dict) and isinstance(record.get("user_id"), int) and isinstance(record.get("path"), str) else None
    except (OSError, ValueError):
        return None


def live(record: dict) -> bool:
    try:
        expires = record.get("expiresAt")
        return expires is None or expires > time.time()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("live failed")
        raise


def find(token: str) -> dict | None:
    """What the link says (whose file, which path), or None when there is no such link or it ran out."""
    try:
        if not TOKEN_PATTERN.match(token):
            return None
        record = read_shares(shares_dir() / f"{token}.json")
        return {**record, "token": token} if record and live(record) else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("find failed")
        raise


def mine(user_id: int) -> list[dict]:
    try:
        home = shares_dir()
        if not home.is_dir():
            return []
        found = []
        for item in home.glob("*.json"):
            record = read_shares(item)
            if record and record["user_id"] == user_id and live(record):
                found.append({**record, "token": item.stem})
        return sorted(found, key=lambda record: record["createdAt"], reverse=True)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mine failed")
        raise


def make(user_id: int, path: str, days: int | None) -> dict:
    """A new link for the file at `path`; the one it had stops working."""
    try:
        for old in mine(user_id):
            if old["path"] == path:
                drop(user_id, old["token"])
        token = secrets.token_urlsafe(TOKEN_BYTES)
        record = {"user_id": user_id, "path": path, "createdAt": time.time(), "expiresAt": time.time() + days * 86400 if days else None}
        shares_dir().mkdir(parents=True, exist_ok=True)
        (shares_dir() / f"{token}.json").write_text(json.dumps(record), encoding="utf-8")
        return {**record, "token": token}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("make failed")
        raise


def drop(user_id: int, token: str) -> bool:
    """Take a link back; False when it is not this person's (or not there)."""
    try:
        if not TOKEN_PATTERN.match(token):
            return False
        target = shares_dir() / f"{token}.json"
        record = read_shares(target)
        if record is None or record["user_id"] != user_id:
            return False
        target.unlink(missing_ok=True)
        return True
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("drop failed")
        raise


def erase_user(user_id: int) -> None:
    try:
        home = shares_dir()
        if not home.is_dir():
            return
        for item in home.glob("*.json"):
            record = read_shares(item)
            if record and record["user_id"] == user_id:
                item.unlink(missing_ok=True)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("erase_user failed")
        raise
