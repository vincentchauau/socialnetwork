"""Derive a unique username handle from a Google email (never exposes the address itself)."""

import re
from typing import Callable

import logging
logger = logging.getLogger(__name__)

MAX_LEN = 32
MIN_LEN = 3
# Besides ASCII letters and digits. '@' is allowed: email flows look users up by users.email only, never by name.
# Deliberately NOT whitespace, control or non-ASCII characters (homoglyphs), nor the separators/metacharacters
# : | / \ " ' < > ` * ? [ ] { } ( ) , ;  (Redis keys and globs, `|`-joined throttle keys, URLs, HTML/mail text,
# shell and SQL LIKE patterns).
ALLOWED_SPECIALS = "._-!#$%&+=^~@"
HANDLE_RE = re.compile(rf"^[A-Za-z0-9{re.escape(ALLOWED_SPECIALS)}]{{{MIN_LEN},{MAX_LEN}}}$")  # case kept for display
ALNUM = re.compile(r"[A-Za-z0-9]")
INVALID = re.compile(r"[^a-z0-9._-]")  # generated handles stay within the conservative core


def is_valid_username(name: str) -> bool:
    """3-32 allowed characters, at least one of them a letter or digit ('...' or '!!!' are refused)."""
    try:
        return HANDLE_RE.fullmatch(name) is not None and ALNUM.search(name) is not None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("is_valid_username failed")
        raise


def key_of(name: str) -> str:
    """The case-insensitive identity of a username: what uniqueness, lookups, reservations and throttles use."""
    try:
        return name.strip().lower()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("key_of failed")
        raise


def base_handle(email: str) -> str:
    try:
        local = INVALID.sub("", email.split("@", 1)[0].lower())[:MAX_LEN]
        return local.ljust(MIN_LEN, "0")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("base_handle failed")
        raise


def unique_handle(email: str, is_taken: Callable[[str], bool]) -> str:
    try:
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
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("unique_handle failed")
        raise
