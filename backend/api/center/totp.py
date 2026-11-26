"""TOTP (RFC 6238) second factor and its single-use recovery codes.

Secrets are stored only as Fernet tokens (key: DATA_KEY when set, else a sub-key of JWT_SECRET under its own
label). Recovery codes are stored only as an HMAC under another JWT_SECRET sub-key. A TOTP time step is accepted
once: the step is recorded with a conditional UPDATE, so a replayed or racing code fails. A recovery code is
consumed with `UPDATE ... WHERE used_at IS NULL`, so two parallel requests cannot both use it.
"""

import base64
import hashlib
import hmac
import secrets
import time

import pyotp
from sqlalchemy import delete, or_, update
from sqlalchemy.orm import Session

from api.center import models
from api.center.audit import audit
from api.center.config import Settings
from api.center.crypto import TemplateCipher
from api.center.models import RecoveryCode, User
from sn_shared.security import get_jwt_secret

import logging
logger = logging.getLogger(__name__)

ISSUER = "Mạng xã hội"
STEP_SECONDS = 30
DIGITS = 6
WINDOW_STEPS = 1  # accepted clock drift: one step either side
RECOVERY_CODES_PER_SET = 10
RECOVERY_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"  # 32 symbols = 5 bits each
RECOVERY_LENGTH = 10  # 50 bits
RECOVERY_GROUPS = (4, 4, 2)  # abcd-efgh-jk
DUMMY_SECRET = pyotp.random_base32()  # spent on failures that have no real secret, so they cost the same


def subkey_totp(label: bytes) -> bytes:
    try:
        return hmac.new(get_jwt_secret().encode(), label, hashlib.sha256).digest()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("subkey_totp failed")
        raise


def make_cipher(settings: Settings) -> TemplateCipher:
    try:
        if not settings.data_key:
            audit.info("TOTP secrets are encrypted with a key derived from JWT_SECRET (set DATA_KEY to decouple them)")
        key = settings.data_key or base64.urlsafe_b64encode(subkey_totp(b"totp-secret-subkey")).decode()
        return TemplateCipher(key)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("make_cipher failed")
        raise


def seal(cipher: TemplateCipher, secret: str) -> str:
    try:
        return cipher.encrypt(secret.encode()).decode()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("seal failed")
        raise


def unseal(cipher: TemplateCipher, token: str | None) -> str | None:
    try:
        plain = cipher.decrypt(token.encode()) if token else None
        if token and plain is None:
            audit.warning("a stored TOTP secret could not be decrypted (corrupt, or DATA_KEY/JWT_SECRET changed)")
        return plain.decode() if plain else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("unseal failed")
        raise


def new_secret() -> str:
    try:
        return pyotp.random_base32()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("new_secret failed")
        raise


def provisioning_uri(secret: str, username: str) -> str:
    """SHA1, 6 digits, 30 s: the defaults every authenticator app supports."""
    try:
        return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS).provisioning_uri(name=username, issuer_name=ISSUER)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("provisioning_uri failed")
        raise


def now_totp() -> float:
    try:
        return time.time()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("now_totp failed")
        raise


def matching_step(secret: str | None, code: str) -> int | None:
    """The time step (within the drift window) whose code equals `code`, else None. Always checks every step."""
    try:
        totp = pyotp.TOTP(secret or DUMMY_SECRET, digits=DIGITS, interval=STEP_SECONDS)
        presented = code.strip().replace(" ", "").encode()
        current = int(now_totp() // STEP_SECONDS)
        found = None
        for step in range(current - WINDOW_STEPS, current + WINDOW_STEPS + 1):
            if hmac.compare_digest(totp.at(step * STEP_SECONDS).encode(), presented) and secret:
                found = step
        return found
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("matching_step failed")
        raise


def accept_step(db: Session, user_id: int, step: int) -> bool:
    """Record `step` as used; False when it is not newer than the last accepted one (replay or lost race)."""
    try:
        result = db.execute(
            update(User)
            .where(User.id == user_id, or_(User.totp_last_step.is_(None), User.totp_last_step < step))
            .values(totp_last_step=step)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("accept_step failed")
        raise


def check_totp(db: Session, cipher: TemplateCipher, user: User, code: str) -> bool:
    """A current code for the user's ENABLED secret, accepted once. The caller commits."""
    try:
        secret = unseal(cipher, user.totp_secret) if user.totp_enabled else None
        step = matching_step(secret, code)
        return step is not None and accept_step(db, user.id, step)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("check_totp failed")
        raise


# --- recovery codes ----------------------------------------------------------------------------------


def normalize_recovery(code: str) -> str:
    try:
        return "".join(ch for ch in code.lower() if ch not in "- \t")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("normalize_recovery failed")
        raise


def recovery_hash(code: str) -> str:
    try:
        return hmac.new(subkey_totp(b"recovery-code-subkey"), normalize_recovery(code).encode(), hashlib.sha256).hexdigest()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("recovery_hash failed")
        raise


def new_recovery_code() -> str:
    try:
        chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_LENGTH))
        groups, start = [], 0
        for size in RECOVERY_GROUPS:
            groups.append(chars[start : start + size])
            start += size
        return "-".join(groups)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("new_recovery_code failed")
        raise


def replace_recovery_codes(db: Session, user_id: int) -> list[str]:
    """Drop the old set and add a fresh one; returns the plain codes (shown once). The caller commits."""
    try:
        db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id).execution_options(synchronize_session=False))
        codes = [new_recovery_code() for _ in range(RECOVERY_CODES_PER_SET)]
        now = models.utcnow()
        db.add_all(RecoveryCode(user_id=user_id, code_hash=recovery_hash(c), created_at=now) for c in codes)
        return codes
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("replace_recovery_codes failed")
        raise


def consume_recovery_code(db: Session, user_id: int, code: str) -> bool:
    """Mark the matching unused code as used; exactly one of any number of racing callers gets True."""
    try:
        result = db.execute(
            update(RecoveryCode)
            .where(
                RecoveryCode.user_id == user_id,
                RecoveryCode.code_hash == recovery_hash(code),
                RecoveryCode.used_at.is_(None),
            )
            .values(used_at=models.utcnow())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("consume_recovery_code failed")
        raise
