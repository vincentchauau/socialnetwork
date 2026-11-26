"""What waits for me in the chat, in numbers: the bar of every app shows them."""

from typing import Annotated

from fastapi import Depends, Query, Request
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.chat import service
from api.chat.db import get_db
from api.chat.models import Room, RoomMember
from api.chat.routes_common import new_router
from api.chat.social import service as social_service

import logging
logger = logging.getLogger(__name__)

MAX_ROOMS_COUNTED = 500
router = new_router()


@router.get("/inbox/summary")
def summary(request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, int]:
    """`messages`: unread messages in my rooms that are not quiet; `requests`: people who ask to write to me and wait for my
    answer; `notices`: notifications of the people side I have not read."""
    try:
        mine = list(
            db.execute(
                select(RoomMember.room_id, RoomMember.notify)
                .join(Room, Room.id == RoomMember.room_id)
                .where(RoomMember.user_id == user.user_id, RoomMember.status == service.JOINED, Room.state != service.DELETED)
                .limit(MAX_ROOMS_COUNTED)
            )
        )
        loud = [room_id for room_id, notify in mine if notify]
        unread = sum(service.unread_counts(db, user.user_id, loud).values())
        requests = db.scalar(
            select(func.count()).select_from(RoomMember).join(Room, Room.id == RoomMember.room_id).where(
                RoomMember.user_id == user.user_id, RoomMember.status == service.PENDING_STATUS, Room.kind == "dm", Room.state != service.DELETED
            )
        ) or 0
        return {"messages": unread, "requests": requests, "notices": social_service.unread_count(db, user.user_id)}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("summary failed")
        raise
