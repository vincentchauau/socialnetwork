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

from app import models
from app.audit import audit
from app.config import Settings
from app.crypto import TemplateCipher
from app.models import RecoveryCode, User
from sn_shared.security import get_jwt_secret

ISSUER = "Mạng xã hội"
STEP_SECONDS = 30
DIGITS = 6
WINDOW_STEPS = 1  # accepted clock drift: one step either side
RECOVERY_CODES_PER_SET = 10
RECOVERY_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"  # 32 symbols = 5 bits each
RECOVERY_LENGTH = 10  # 50 bits
RECOVERY_GROUPS = (4, 4, 2)  # abcd-efgh-jk
_DUMMY_SECRET = pyotp.random_base32()  # spent on failures that have no real secret, so they cost the same


def _subkey(label: bytes) -> bytes:
    return hmac.new(get_jwt_secret().encode(), label, hashlib.sha256).digest()


def make_cipher(settings: Settings) -> TemplateCipher:
    if not settings.data_key:
        audit.info("TOTP secrets are encrypted with a key derived from JWT_SECRET (set DATA_KEY to decouple them)")
    key = settings.data_key or base64.urlsafe_b64encode(_subkey(b"totp-secret-subkey")).decode()
    return TemplateCipher(key)


def seal(cipher: TemplateCipher, secret: str) -> str:
    return cipher.encrypt(secret.encode()).decode()


def unseal(cipher: TemplateCipher, token: str | None) -> str | None:
    plain = cipher.decrypt(token.encode()) if token else None
    if token and plain is None:
        audit.warning("a stored TOTP secret could not be decrypted (corrupt, or DATA_KEY/JWT_SECRET changed)")
    return plain.decode() if plain else None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    """SHA1, 6 digits, 30 s: the defaults every authenticator app supports."""
    return pyotp.TOTP(secret, digits=DIGITS, interval=STEP_SECONDS).provisioning_uri(name=username, issuer_name=ISSUER)


def _now() -> float:
    return time.time()


def matching_step(secret: str | None, code: str) -> int | None:
    """The time step (within the drift window) whose code equals `code`, else None. Always checks every step."""
    totp = pyotp.TOTP(secret or _DUMMY_SECRET, digits=DIGITS, interval=STEP_SECONDS)
    presented = code.strip().replace(" ", "").encode()
    current = int(_now() // STEP_SECONDS)
    found = None
    for step in range(current - WINDOW_STEPS, current + WINDOW_STEPS + 1):
        if hmac.compare_digest(totp.at(step * STEP_SECONDS).encode(), presented) and secret:
            found = step
    return found


def accept_step(db: Session, user_id: int, step: int) -> bool:
    """Record `step` as used; False when it is not newer than the last accepted one (replay or lost race)."""
    result = db.execute(
        update(User)
        .where(User.id == user_id, or_(User.totp_last_step.is_(None), User.totp_last_step < step))
        .values(totp_last_step=step)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def check_totp(db: Session, cipher: TemplateCipher, user: User, code: str) -> bool:
    """A current code for the user's ENABLED secret, accepted once. The caller commits."""
    secret = unseal(cipher, user.totp_secret) if user.totp_enabled else None
    step = matching_step(secret, code)
    return step is not None and accept_step(db, user.id, step)


# --- recovery codes ----------------------------------------------------------------------------------


def normalize_recovery(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch not in "- \t")


def recovery_hash(code: str) -> str:
    return hmac.new(_subkey(b"recovery-code-subkey"), normalize_recovery(code).encode(), hashlib.sha256).hexdigest()


def new_recovery_code() -> str:
    chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(RECOVERY_LENGTH))
    groups, start = [], 0
    for size in RECOVERY_GROUPS:
        groups.append(chars[start : start + size])
        start += size
    return "-".join(groups)


def replace_recovery_codes(db: Session, user_id: int) -> list[str]:
    """Drop the old set and add a fresh one; returns the plain codes (shown once). The caller commits."""
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id).execution_options(synchronize_session=False))
    codes = [new_recovery_code() for _ in range(RECOVERY_CODES_PER_SET)]
    now = models.utcnow()
    db.add_all(RecoveryCode(user_id=user_id, code_hash=recovery_hash(c), created_at=now) for c in codes)
    return codes


def consume_recovery_code(db: Session, user_id: int, code: str) -> bool:
    """Mark the matching unused code as used; exactly one of any number of racing callers gets True."""
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
