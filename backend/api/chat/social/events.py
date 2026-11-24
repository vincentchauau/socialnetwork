"""The account events of `center` that reach the people of the social network (delivered at least once, so: idempotent).

Deletion: their friendships and blocks, the virtual people they drew, and the notifications that came from them or are for them are
removed (nothing of it is a conversation others took part in). A report they made stays, with no reporter (`0`); a report about
them stays too, as the evidence it is. Rename: nothing to do (names are read from `users`). (The person is a row of `users`: center
keeps it.)
"""

from sqlalchemy import delete, or_, update
from sqlalchemy.orm import Session

from api.chat.social.models import Edge, Notification, Report

DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id <= DELETED_USER_ID:
        return
    db.execute(delete(Edge).where(or_(Edge.src_id == user_id, Edge.dst_id == user_id)))  # friendships, blocks and companions alike
    db.execute(delete(Notification).where(or_(Notification.user_id == user_id, Notification.actor_id == user_id)))
    db.execute(update(Report).where(Report.reporter_id == user_id).values(reporter_id=DELETED_USER_ID))


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """A notice keeps only the id of whoever did it: the name is read from `users`, so nothing follows a rename."""
    return None
