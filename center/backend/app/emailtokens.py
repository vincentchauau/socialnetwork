"""Single-use email tokens (verify / login / reset / reauth): a link token and an optional 6-digit code per row.

Only hashes are stored: SHA-256 of the link token, and an HMAC of the code keyed with a sub-key of
JWT_SECRET and bound to the row id (a database leak alone cannot brute-force a 6-digit code).
Every token is consumed with a conditional UPDATE, so two concurrent submissions cannot both succeed.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.models import EmailToken, User
from sn_shared.security import get_jwt_secret

VERIFY = "verify"
LOGIN = "login"
RESET = "reset"
REAUTH = "reauth"  # a code only: the link of its row is never sent

VERIFY_TTL = timedelta(hours=24)
LOGIN_TTL = timedelta(minutes=15)  # the code and the link of one login mail
RESET_TTL = timedelta(minutes=30)
REAUTH_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5
MAX_LIVE_TOKENS = 3  # live (unused) tokens kept per (user, purpose)
CODE_DIGITS = 6
TOKEN_BYTES = 32

def _NO_SYNC(statement):
    """Bulk UPDATE/DELETE straight on the database: the in-Python matcher cannot compare SQLite's naive datetimes."""
    return statement.execution_options(synchronize_session=False)


_TTL = {VERIFY: VERIFY_TTL, LOGIN: LOGIN_TTL, RESET: RESET_TTL, REAUTH: REAUTH_TTL}


@dataclass(frozen=True)
class Issued:
    token: str
    code: str | None


def _now() -> datetime:
    return models.utcnow()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _code_key() -> bytes:
    return hmac.new(get_jwt_secret().encode(), b"email-code-subkey", hashlib.sha256).digest()


def code_mac(row_id: int, code: str) -> str:
    return hmac.new(_code_key(), f"{row_id}:{code}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def purge(db: Session) -> None:
    """Drop expired and used rows (called on writes, so the table cannot grow without bound)."""
    db.execute(_NO_SYNC(delete(EmailToken).where(or_(EmailToken.expires_at < _now(), EmailToken.used_at.is_not(None)))))


def _insert(db: Session, user_id: int, purpose: str, email: str, token: str, code: str | None) -> EmailToken:
    now = _now()
    row = EmailToken(
        user_id=user_id, purpose=purpose, email=email, token_hash=hash_token(token),
        expires_at=now + _TTL[purpose], created_at=now,
    )  # fmt: skip
    db.add(row)
    db.flush()  # the code is bound to the row id
    if code is not None:
        row.code_hash = code_mac(row.id, code)
    return row


def _trim_live(db: Session, user_id: int, purpose: str) -> None:
    """Keep the newest MAX_LIVE_TOKENS unused rows of this purpose; a stranger's requests cannot wipe them all."""
    stale = db.scalars(
        select(EmailToken.id)
        .where(EmailToken.user_id == user_id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .order_by(EmailToken.id.desc())
        .offset(MAX_LIVE_TOKENS)
    ).all()
    if stale:
        db.execute(_NO_SYNC(delete(EmailToken).where(EmailToken.id.in_(stale))))


def _rehearse(db: Session, purpose: str, email: str, token: str, code: str | None) -> None:
    """The database work of an issue for an address nobody owns: insert under a savepoint, then roll it back."""
    owner = db.scalar(select(User.id).limit(1))
    savepoint = db.begin_nested()
    try:
        if owner is not None:
            _insert(db, owner, purpose, email, token, code)
            _trim_live(db, owner, purpose)
    except IntegrityError:
        pass  # a placeholder that cannot be stored is still the same work
    finally:
        savepoint.rollback()


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
        _rehearse(db, purpose, email, token, code)
        db.commit()
        return Issued(token, code)
    _insert(db, user.id, purpose, email, token, code)
    _trim_live(db, user.id, purpose)
    db.commit()
    return Issued(token, code)


def _live(purpose: str):
    """Not used and not expired (a wrong-code counter never kills the link)."""
    return (
        EmailToken.purpose == purpose,
        EmailToken.used_at.is_(None),
        EmailToken.expires_at > _now(),
    )


def find_by_token(db: Session, token: str, purpose: str) -> EmailToken | None:
    if not token or len(token) > 200:
        return None
    return db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_token(token), *_live(purpose)))


def find_for_user(db: Session, user_id: int, purpose: str, email: str | None = None) -> EmailToken | None:
    """The user's live token whose CODE can still be tried (newest first), optionally for one address."""
    query = select(EmailToken).where(
        EmailToken.user_id == user_id, EmailToken.attempts < MAX_CODE_ATTEMPTS, *_live(purpose)
    )
    if email is not None:
        query = query.where(EmailToken.email == email)
    return db.scalar(query.order_by(EmailToken.id.desc()))


def check_code(db: Session, row: EmailToken | None, code: str) -> bool:
    """Count one attempt (atomically, and persist it) and compare the code in constant time.

    After MAX_CODE_ATTEMPTS attempts the row's CODE accepts nothing more, not even the right code
    (its link stays valid until the TTL).
    A missing row costs the same MAC so the caller cannot tell an unknown address from a wrong code.
    """
    code = code.strip()
    if row is None:
        hmac.compare_digest(code_mac(0, code), code_mac(0, ""))
        return False
    counted = db.execute(
        _NO_SYNC(
            update(EmailToken)
            .where(EmailToken.id == row.id, EmailToken.used_at.is_(None), EmailToken.attempts < MAX_CODE_ATTEMPTS)
            .values(attempts=EmailToken.attempts + 1)
        )
    )
    db.commit()
    if counted.rowcount != 1 or row.code_hash is None:
        return False
    return hmac.compare_digest(code_mac(row.id, code), row.code_hash)


def consume(db: Session, row_id: int) -> bool:
    """Mark the token used; True for exactly one caller (the caller commits)."""
    result = db.execute(
        _NO_SYNC(
            update(EmailToken)
            .where(EmailToken.id == row_id, EmailToken.used_at.is_(None), EmailToken.expires_at > _now())
            .values(used_at=_now())
        )
    )
    return result.rowcount == 1
