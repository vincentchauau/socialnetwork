"""Derive a unique username handle from a Google email (never exposes the address itself)."""

import re
from typing import Callable

HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")  # capitalisation is kept for display only
_INVALID = re.compile(r"[^a-z0-9._-]")
MAX_LEN = 32
MIN_LEN = 3


def key_of(name: str) -> str:
    """The case-insensitive identity of a username: what uniqueness, lookups, reservations and throttles use."""
    return name.strip().lower()


def base_handle(email: str) -> str:
    local = _INVALID.sub("", email.split("@", 1)[0].lower())[:MAX_LEN]
    return local.ljust(MIN_LEN, "0")


def unique_handle(email: str, is_taken: Callable[[str], bool]) -> str:
    base = base_handle(email)
    if not is_taken(base):
        return base
    suffix = 2
    while True:
        tail = str(suffix)
        candidate = base[: MAX_LEN - len(tail)] + tail
        if not is_taken(candidate):
            return candidate
        suffix += 1
