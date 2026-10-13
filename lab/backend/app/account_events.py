"""Reactions to account events published by `center` (delivered at least once).

Deletion removes the user's lab_events rows (idempotent). Kafka messages already in the topic cannot be
deleted: they are keyed by the numeric user id only (no name) and expire by the topic retention (1 hour).
A rename needs nothing: no username is stored. Handlers never commit.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import LabEvent


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id <= 0:
        return
    db.execute(delete(LabEvent).where(LabEvent.user_id == user_id))


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    return None
