"""The storage and the one-time-use rules shared by email tokens and SMS codes (table `verification_codes`).

`emailtokens` and `phones` own what differs (lifetimes, link token, key of the code MAC, sending); everything else is
here: prune, keep-the-newest, live/attempt filters, counting an attempt and consuming a row atomically.
"""

import hmac
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.center import models
from api.center.models import User, VerificationCode

EMAIL = "email"
PHONE = "phone"
MAX_CODE_ATTEMPTS = 5

CodeMac = Callable[[int, str], str]


def no_sync(statement):
    """Bulk UPDATE/DELETE straight on the database: the in-Python matcher cannot compare SQLite's naive datetimes."""
    return statement.execution_options(synchronize_session=False)


def now() -> datetime:
    return models.utcnow()


def purge(db: Session) -> None:
    """Drop expired and used rows (called on writes, so the table cannot grow without bound)."""
    db.execute(no_sync(delete(VerificationCode).where(
        or_(VerificationCode.expires_at < now(), VerificationCode.used_at.is_not(None)))))


def insert(
    db: Session, user_id: int, channel: str, purpose: str, target: str, ttl: timedelta,
    *, token_hash: str | None = None, code: str | None = None, mac: CodeMac | None = None,
) -> VerificationCode:
    row = VerificationCode(
        user_id=user_id, channel=channel, purpose=purpose, target=target, token_hash=token_hash,
        expires_at=now() + ttl,
    )  # fmt: skip
    db.add(row)
    db.flush()  # the code is bound to the row id
    if code is not None and mac is not None:
        row.code_hash = mac(row.id, code)
    return row


def trim_live(db: Session, user_id: int, channel: str, purpose: str, keep: int) -> None:
    """Keep the newest `keep` unused rows of this (user, channel, purpose); a stranger's requests cannot wipe them all."""
    stale = db.scalars(
        select(VerificationCode.id)
        .where(
            VerificationCode.user_id == user_id, VerificationCode.channel == channel,
            VerificationCode.purpose == purpose, VerificationCode.used_at.is_(None),
        )
        .order_by(VerificationCode.id.desc())
        .offset(keep)
    ).all()
    if stale:
        db.execute(no_sync(delete(VerificationCode).where(VerificationCode.id.in_(stale))))


def rehearse(db: Session, store: Callable[[int], None]) -> None:
    """The database work of an issue for a target nobody owns: `store(owner_id)` under a savepoint, rolled back."""
    owner = db.scalar(select(User.id).limit(1))
    savepoint = db.begin_nested()
    try:
        if owner is not None:
            store(owner)
    except IntegrityError:
        pass  # a placeholder that cannot be stored is still the same work
    finally:
        savepoint.rollback()


def live(channel: str, purpose: str):
    """Not used and not expired (a wrong-code counter never kills an email link)."""
    return (
        VerificationCode.channel == channel,
        VerificationCode.purpose == purpose,
        VerificationCode.used_at.is_(None),
        VerificationCode.expires_at > now(),
    )


def find_for_user(
    db: Session, user_id: int, channel: str, purpose: str, target: str | None = None
) -> VerificationCode | None:
    """The user's newest live row whose CODE can still be tried, optionally for one address or number."""
    query = select(VerificationCode).where(
        VerificationCode.user_id == user_id, VerificationCode.attempts < MAX_CODE_ATTEMPTS, *live(channel, purpose)
    )
    if target is not None:
        query = query.where(VerificationCode.target == target)
    return db.scalar(query.order_by(VerificationCode.id.desc()))


def check_code(db: Session, row: VerificationCode | None, code: str, mac: CodeMac) -> bool:
    """Count one attempt (atomically, persisted) and compare the code in constant time.

    After MAX_CODE_ATTEMPTS attempts the row's CODE accepts nothing more, not even the right one.
    A missing row costs the same MAC so the caller cannot tell an unknown target from a wrong code.
    """
    code = code.strip()
    if row is None:
        hmac.compare_digest(mac(0, code), mac(0, ""))
        return False
    counted = db.execute(
        no_sync(
            update(VerificationCode)
            .where(
                VerificationCode.id == row.id, VerificationCode.used_at.is_(None),
                VerificationCode.attempts < MAX_CODE_ATTEMPTS,
            )
            .values(attempts=VerificationCode.attempts + 1)
        )
    )
    db.commit()
    if counted.rowcount != 1 or row.code_hash is None:
        return False
    return hmac.compare_digest(mac(row.id, code), row.code_hash)


def consume(db: Session, row_id: int) -> bool:
    """Mark the row used; True for exactly one caller (the caller commits)."""
    result = db.execute(
        no_sync(
            update(VerificationCode)
            .where(
                VerificationCode.id == row_id, VerificationCode.used_at.is_(None),
                VerificationCode.expires_at > now(),
            )
            .values(used_at=now())
        )
    )
    return result.rowcount == 1
