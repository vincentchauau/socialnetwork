"""Username availability: taken by an account, or reserved for 30 days by the person who just gave it up."""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ReservedUsername, User, utcnow
from app.usersessions import as_utc

RENAME_INTERVAL = timedelta(days=30)  # at most one rename per account in this window
RESERVATION = timedelta(days=30)  # how long a released name stays reserved for its previous owner


def can_rename_after(user: User) -> datetime | None:
    """When the user may rename again, or None when they may do so now."""
    if user.username_changed_at is None:
        return None
    moment = as_utc(user.username_changed_at) + RENAME_INTERVAL
    return moment if moment > utcnow() else None


# Names that look official; never given to a user (generated `user-xxxxxx` handles are unaffected).
SYSTEM_NAMES = frozenset(
    "admin administrator root support system moderator staff help security postmaster abuse null undefined "
    "api www mail noreply no-reply center chat photos watch werewolf market learning jobs".split()
)


def unavailable(db: Session, username: str, user_id: int | None = None) -> bool:
    """True when `username` is a system name, belongs to another account, or is reserved for another one
    (`user_id` may use its own reservation)."""
    if username.lower() in SYSTEM_NAMES:
        return True
    taken = select(User.id).where(func.lower(User.username) == username.lower())
    if user_id is not None:
        taken = taken.where(User.id != user_id)
    if db.scalar(taken) is not None:
        return True
    reserved = select(ReservedUsername.user_id).where(
        func.lower(ReservedUsername.username) == username.lower(), ReservedUsername.until > utcnow()
    )
    owner = db.scalar(reserved)
    return owner is not None and owner != user_id


def reserve(db: Session, username: str, user_id: int) -> None:
    """Reserve `username` for `user_id` (replacing an expired or own earlier reservation). Caller commits."""
    db.merge(ReservedUsername(username=username, user_id=user_id, until=utcnow() + RESERVATION))


def release(db: Session, username: str) -> None:
    db.execute(delete(ReservedUsername).where(ReservedUsername.username == username))
