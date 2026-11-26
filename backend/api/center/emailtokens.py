"""Single-use email tokens (verify / login / reset / reauth): a link token and an optional 6-digit code per row.

Only hashes are stored: SHA-256 of the link token, and an HMAC of the code keyed with a sub-key of
JWT_SECRET and bound to the row id (a database leak alone cannot brute-force a 6-digit code).
Every token is consumed with a conditional UPDATE, so two concurrent submissions cannot both succeed.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.center import codes
from api.center.codes import MAX_CODE_ATTEMPTS, consume, purge  # noqa: F401  (re-exported: the routes use them from here)
from api.center.models import User, VerificationCode
from sn_shared.security import get_jwt_secret
from sn_shared.tokens import hash_token

VERIFY = "verify"
LOGIN = "login"
RESET = "reset"
REAUTH = "reauth"  # a code only: the link of its row is never sent

VERIFY_TTL = timedelta(hours=24)
LOGIN_TTL = timedelta(minutes=15)  # the code and the link of one login mail
RESET_TTL = timedelta(minutes=30)
REAUTH_TTL = timedelta(minutes=10)
MAX_LIVE_TOKENS = 3  # live (unused) tokens kept per (user, purpose)
CODE_DIGITS = 6
TOKEN_BYTES = 32

_TTL = {VERIFY: VERIFY_TTL, LOGIN: LOGIN_TTL, RESET: RESET_TTL, REAUTH: REAUTH_TTL}


@dataclass(frozen=True)
class Issued:
    token: str
    code: str | None


def code_key() -> bytes:
    return hmac.new(get_jwt_secret().encode(), b"email-code-subkey", hashlib.sha256).digest()


def code_mac(row_id: int, code: str) -> str:
    return hmac.new(code_key(), f"{row_id}:{code}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def _store(db: Session, user_id: int, purpose: str, email: str, token: str, code: str | None) -> None:
    codes.insert(
        db, user_id, codes.EMAIL, purpose, email, _TTL[purpose],
        token_hash=hash_token(token), code=code, mac=code_mac,
    )  # fmt: skip
    codes.trim_live(db, user_id, codes.EMAIL, purpose, MAX_LIVE_TOKENS)


def issue(db: Session, user: User | None, purpose: str, email: str, *, with_code: bool) -> Issued:
    """Create a token for `user`, keeping at most MAX_LIVE_TOKENS live ones of this purpose (oldest dropped).

    With `user=None` (an address that belongs to nobody) the same hashing and database work is done
    (an insert under a savepoint that is rolled back) and nothing is stored, so the caller's response
    does not depend on the account existing.
    """
    purge(db)
    token = secrets.token_urlsafe(TOKEN_BYTES)
    code = new_code() if with_code else None
    if user is None:
        codes.rehearse(db, lambda owner: _store(db, owner, purpose, email, token, code))
    else:
        _store(db, user.id, purpose, email, token, code)
    db.commit()
    return Issued(token, code)


def find_by_token(db: Session, token: str, purpose: str) -> VerificationCode | None:
    if not token or len(token) > 200:
        return None
    return db.scalar(
        select(VerificationCode).where(
            VerificationCode.token_hash == hash_token(token), *codes.live(codes.EMAIL, purpose)
        )
    )


def find_for_user(db: Session, user_id: int, purpose: str, email: str | None = None) -> VerificationCode | None:
    """The user's live token whose CODE can still be tried (newest first), optionally for one address."""
    return codes.find_for_user(db, user_id, codes.EMAIL, purpose, email)


def check_code(db: Session, row: VerificationCode | None, code: str) -> bool:
    """Count one attempt and compare the code; after MAX_CODE_ATTEMPTS the CODE is dead (the link lives to the TTL)."""
    return codes.check_code(db, row, code, code_mac)
