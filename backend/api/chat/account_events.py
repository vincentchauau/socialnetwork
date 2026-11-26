"""Reactions to account events published by `center` (delivered at least once).

Data model: `rooms` (user_id: the owner), `room_members` (user_id), `messages` (user_id, content). Names are not kept here: they are read
from `users` of center (`sn_shared.directory`), so a rename needs nothing.

Nothing is removed. Deletion: messages are part of a conversation other people took part in, so their rows are KEPT and
ANONYMIZED: `user_id` becomes the tombstone 0 (center ids start at 1), which is read as DELETED_USERNAME, also on the person's
memberships, which become `left`. A room they owned goes to its member with the lowest id; a room with nobody
else in it, and a chat of two, is closed. Rename: nothing to do.

The people side (`api.chat.social.events`) goes with the account too: its friendships, blocks, drawn virtual people and notices are
removed, and what it reported stays with no reporter.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sn_shared import directory
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.chat import service
from api.chat.social import events as social_events

from api.chat.models import Meeting, Message, Room, RoomMember

import logging
logger = logging.getLogger(__name__)

DELETED_USERNAME = directory.DELETED_USERNAME
DELETED_USER_ID = 0
GONE = "the account was deleted"


def on_user_deleted(db: Session, user_id: int, old_username: str | None = None) -> None:
    try:
        if user_id == DELETED_USER_ID:
            return
        social_events.on_user_deleted(db, user_id)
        old_name = old_username or directory.name_of(db, user_id)  # the event carries the name: center has removed the row by now
        for room in db.scalars(select(Room).where(Room.user_id == user_id, Room.state != service.DELETED)).all():
            heir = service.transfer_target(db, room, user_id) if room.kind == "chat" else None
            if heir is None:
                service.set_state(db, room, service.CLOSED, reason=GONE)  # a chat of two is over when one is gone
            else:
                room.user_id = heir.user_id
        db.flush()
        for room in db.scalars(select(Room).where(Room.kind == "dm", Room.id.in_(select(RoomMember.room_id).where(RoomMember.user_id == user_id)))).all():
            service.set_state(db, room, service.CLOSED, reason=GONE)
        members = db.scalars(select(RoomMember).where(RoomMember.user_id == user_id)).all()
        if members and old_name != DELETED_USERNAME:
            rename_in_lines(db, old_name, DELETED_USERNAME)
        for member in members:
            if member.status in (service.JOINED, service.PENDING_STATUS):
                room = db.get(Room, member.room_id)
                service.set_status(db, room, member, service.LEFT, reason=GONE)
        db.execute(update(Message).where(Message.user_id == user_id).values(user_id=DELETED_USER_ID))
        db.execute(update(Meeting).where(Meeting.started_by == user_id).values(started_by=DELETED_USER_ID))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_deleted failed")
        raise


def rename_in_lines(db: Session, old_name: str, new_name: str) -> None:
    """The lines of `system` hold the name of the person they are about at the end of the content (`kicked:bob`)."""
    try:
        suffix = f":{old_name}"
        for line in db.scalars(select(Message).where(Message.kind == "system", Message.content.endswith(suffix, autoescape=True))):
            line.content = line.content[: -len(old_name)] + new_name
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("rename_in_lines failed")
        raise


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """Names are read from `users`: nothing to change here."""
    try:
        return None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_renamed failed")
        raise
