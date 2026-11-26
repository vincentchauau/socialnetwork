"""Password policy and scrypt hashing (legacy bcrypt hashes still verify)."""

import base64
import hashlib
import hmac
import os
import unicodedata

from sn_shared.security import verify_password as verify_bcrypt

import logging
logger = logging.getLogger(__name__)

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1  # about 32 MB of memory per hash
SCRYPT_MAXMEM = 128 * 1024 * 1024
SALT_BYTES = 16
DIGEST_BYTES = 32  # keeps the stored hash at 86 characters (column is String(100))
MIN_PASSWORD = 8
MAX_PASSWORD = 128
CLASS_RULE_MESSAGE = "Password must contain a lowercase letter, an uppercase letter, a digit and a special character"
# Stored for accounts without a password (Google-only); verify_password always rejects it.
NO_PASSWORD = "!"
COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "12345678", "123456789", "1234567890",
        "qwertyuiop", "qwerty123", "iloveyou", "11111111", "00000000", "abc12345",
        "letmein123", "welcome123", "admin1234", "passw0rd", "p@ssw0rd", "p@ssword1", "pssw0rd",
    }
)  # fmt: skip


def alphanumeric(text: str) -> str:
    try:
        return "".join(c for c in text if c.isalnum())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("alphanumeric failed")
        raise


def missing_character_classes(password: str) -> list[str]:
    """Which of the four classes (lower, upper, digit, special) the password lacks."""
    try:
        present = {
            "lower": any(c.islower() for c in password),
            "upper": any(c.isupper() for c in password),
            "digit": any(c.isdigit() for c in password),
            "special": any(not c.isalnum() for c in password),
        }
        return [name for name, ok in present.items() if not ok]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("missing_character_classes failed")
        raise


def password_problem(password: str) -> str | None:
    """Why the password is rejected, or None when acceptable."""
    try:
        if len(password) < MIN_PASSWORD:
            return f"Password must be at least {MIN_PASSWORD} characters"
        if len(password) > MAX_PASSWORD:
            return f"Password must be at most {MAX_PASSWORD} characters"
        if missing_character_classes(password):
            return CLASS_RULE_MESSAGE
        lowered = password.lower()
        if lowered in COMMON_PASSWORDS or alphanumeric(lowered) in COMMON_PASSWORDS:  # "Password1!" is still "password1"
            return "Password is too common"
        return None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("password_problem failed")
        raise


def scrypt_passwords(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    try:
        normalized = unicodedata.normalize("NFKC", password)
        return hashlib.scrypt(normalized.encode(), salt=salt, n=n, r=r, p=p, maxmem=SCRYPT_MAXMEM, dklen=DIGEST_BYTES)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("scrypt_passwords failed")
        raise


def hash_password(password: str) -> str:
    """Self-describing 'scrypt$n$r$p$salt$hash' so the cost can be raised later."""
    try:
        salt = os.urandom(SALT_BYTES)
        digest = scrypt_passwords(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
        return "$".join(
            ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
             base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
        )  # fmt: skip
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("hash_password failed")
        raise


def is_legacy_bcrypt(stored: str) -> bool:
    try:
        return stored.startswith("$2")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("is_legacy_bcrypt failed")
        raise


def has_password(stored: str) -> bool:
    try:
        return stored != NO_PASSWORD
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("has_password failed")
        raise


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
        actual = scrypt_passwords(password, base64.b64decode(salt_b64), int(n), int(r), int(p))
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
