"""Password policy and scrypt hashing (legacy bcrypt hashes still verify)."""

import base64
import hashlib
import hmac
import os
import unicodedata

from sn_shared.security import verify_password as verify_bcrypt

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1  # about 32 MB of memory per hash
SCRYPT_MAXMEM = 128 * 1024 * 1024
SALT_BYTES = 16
DIGEST_BYTES = 32  # keeps the stored hash at 86 characters (column is String(100))
MIN_PASSWORD = 8
MAX_PASSWORD = 128
# Stored for accounts without a password (Google-only); verify_password always rejects it.
NO_PASSWORD = "!"
COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "12345678", "123456789", "1234567890",
        "qwertyuiop", "qwerty123", "iloveyou", "11111111", "00000000", "abc12345",
        "letmein123", "welcome123", "admin1234",
    }
)  # fmt: skip


def password_problem(password: str, username: str = "") -> str | None:
    """Why the password is rejected, or None when acceptable."""
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters"
    if len(password) > MAX_PASSWORD:
        return f"Password must be at most {MAX_PASSWORD} characters"
    if len(set(password)) < 4:
        return "Password is too simple (too few distinct characters)"
    if password.lower() in COMMON_PASSWORDS:
        return "Password is too common"
    if username and password.lower() == username.lower():
        return "Password must not equal the username"
    return None


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    normalized = unicodedata.normalize("NFKC", password)
    return hashlib.scrypt(normalized.encode(), salt=salt, n=n, r=r, p=p, maxmem=SCRYPT_MAXMEM, dklen=DIGEST_BYTES)


def hash_password(password: str) -> str:
    """Self-describing 'scrypt$n$r$p$salt$hash' so the cost can be raised later."""
    salt = os.urandom(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return "$".join(
        ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
         base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
    )  # fmt: skip


def is_legacy_bcrypt(stored: str) -> bool:
    return stored.startswith("$2")


def has_password(stored: str) -> bool:
    return stored != NO_PASSWORD


def verify_password(password: str, stored: str | None) -> bool:
    password = password[:MAX_PASSWORD]  # never hash an unbounded input
    if not stored or stored == NO_PASSWORD:
        return False
    if is_legacy_bcrypt(stored):
        return verify_bcrypt(password[:72], stored)
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = _scrypt(password, base64.b64decode(salt_b64), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    """True for bcrypt hashes and scrypt hashes with older parameters."""
    if stored == NO_PASSWORD:
        return False
    try:
        scheme, n, r, p, *_ = stored.split("$")
        return scheme != "scrypt" or (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    except ValueError:
        return True
