"""Reactions to account events published by `center` (delivered at least once).

Data model: `messages` (room, user_id, username, content). Messages are part of a
conversation other people took part in, so on deletion the rows are KEPT and
ANONYMIZED: `user_id` becomes the tombstone 0 (center ids start at 1) and
`username` becomes DELETED_USERNAME. Nothing is removed. On rename every
message of that user id gets the new username.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Message

DELETED_USERNAME = "Người dùng đã xóa"
DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(
        update(Message)
        .where(Message.user_id == user_id)
        .values(user_id=DELETED_USER_ID, username=DELETED_USERNAME)
    )


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(update(Message).where(Message.user_id == user_id).values(username=new_username))
