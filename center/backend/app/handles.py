"""Derive a unique username handle from a Google email (never exposes the address itself)."""

import re
from typing import Callable

HANDLE_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
_INVALID = re.compile(r"[^a-z0-9._-]")
MAX_LEN = 32
MIN_LEN = 3


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
