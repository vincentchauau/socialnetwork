"""Reactions to account events published by `center` (delivered at least once).

Deletion removes all of the user's measurements. No username is stored, so a
rename needs nothing. Handlers are idempotent and never commit.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Measurement


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id <= 0:
        return
    db.execute(delete(Measurement).where(Measurement.user_id == user_id))


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    return None
