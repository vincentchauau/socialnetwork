"""What the routes of rooms share: the checks every write goes through, sending to sockets, and who may see or do what."""

from typing import Annotated

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload
from sqlalchemy.orm import Session

from api.chat import service
from api.chat.models import Message, Room, RoomMember
from sn_shared.origin import allowed_origins

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
from api.chat.schemas import (
    ROOM_PATTERN,
    LastMessage,
    MessageOut,
    MyMembership,
    RoomOut,
    SearchHit,
)

LIST_DEFAULT_LIMIT = 50
LIST_MAX_LIMIT = 100
HISTORY_DEFAULT_LIMIT = 50
HISTORY_MAX_LIMIT = 200
FORBIDDEN_ORIGIN = "Origin not allowed"
Slug = Annotated[str, Path(pattern=ROOM_PATTERN)]


def same_origin(request: Request) -> None:
    """A browser always names the page a write comes from; a foreign or missing one is refused (cookies ride along)."""
    if request.method in SAFE_METHODS:
        return
    if request.headers.get("origin") not in allowed_origins():
        raise HTTPException(status.HTTP_403_FORBIDDEN, FORBIDDEN_ORIGIN)


TOO_MANY_REQUESTS = "Too many requests"


def throttle(request: Request, user: TokenPayload = Depends(get_current_user)) -> None:
    """One person may only write so often (reads are free): a script in a loop is slowed down, a person never notices."""
    if request.method not in SAFE_METHODS and not request.app.state.write_throttle.allow(user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_REQUESTS)


def new_router() -> APIRouter:
    """A router whose every route checks the origin of a write and the rate of the writer."""
    return APIRouter(dependencies=[Depends(same_origin), Depends(throttle)])


def emit(request: Request, slug: str, payload: dict) -> None:
    """Send a frame to the room's open sockets, from a route that runs in a worker thread."""
    anyio.from_thread.run(request.app.state.hub.broadcast, slug, payload)


def disconnect(request: Request, slug: str, user_id: int, reason: str) -> None:
    anyio.from_thread.run(request.app.state.disconnect, slug, user_id, reason)


def changed(request: Request, db: Session) -> None:
    """A room was made, changed or removed: the list of public rooms the lobby may name, and its version, move on."""
    state = request.app.state
    state.public_slugs = service.public_slugs(db)
    state.rooms_version += 1
    anyio.from_thread.run(state.lobby.notify)
    anyio.from_thread.run(state.cluster_changed)  # and the other copies of the chat


def announce(request: Request, slug: str, lines: list[Message]) -> None:
    """Show the lines about a change (already saved) to whoever has the room open."""
    for line in lines:
        emit(request, slug, MessageOut.model_validate(line).frame())


def online_of(request: Request, slug: str) -> int:
    return request.app.state.presence.members(slug)[1]


def room_out(
    request: Request, room: Room, members: int, me: RoomMember | None, unread: int = 0, hit: SearchHit | None = None, last: dict | None = None, owner_name: str = "",
    title: str | None = None, avatar: str | None = None,
) -> RoomOut:
    return RoomOut(
        id=room.id, slug=room.slug, kind=room.kind, title=title or room.title, category=room.category, avatar=avatar or room.avatar, user_id=room.user_id, owner_name=owner_name,
        visibility=room.visibility, join_policy=room.join_policy, capacity=room.capacity, state=room.state, members=members, online=online_of(request, room.slug),
        me=MyMembership(role=service.role_of(room, me), status=me.status, muted=me.muted, unread=unread, notify=me.notify, last_read=me.last_read_message_id or 0) if me else None,
        hit=hit, last_message=LastMessage(**last) if last else None,
    )  # fmt: skip


def visible(db: Session, slug: str, user: TokenPayload) -> tuple[Room, RoomMember | None]:
    """The room and my membership, or 404: a private room does not exist for anyone who is not in it."""
    room = service.room_by_slug(db, slug)
    me = service.member_of(db, room.id, user.user_id) if room else None
    if room is None or (room.state == service.DELETED and room.user_id != user.user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, service.NOT_FOUND)  # a deleted room is hidden, but its owner can get it back
    asked = room.kind == "dm" and me is not None and me.status == service.PENDING_STATUS  # a request to write: read what it says
    if room.visibility == "private" and (me is None or (me.status not in service.READERS and not asked)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, service.NOT_FOUND)
    return room, me


def owner_of(db: Session, slug: str, user: TokenPayload) -> tuple[Room, RoomMember]:
    room, me = visible(db, slug, user)
    if not service.is_owner(room, me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can do this")
    return room, me


def one_out(request: Request, db: Session, room: Room, me: RoomMember | None, user: TokenPayload) -> RoomOut:
    unread = service.unread_counts(db, user.user_id, [room.id]).get(room.id, 0) if me else 0
    return room_out(
        request, room, service.joined_members(db, room.id), me, unread, owner_name=service.owner_names(db, [room]).get(room.id, ""),
        title=service.dm_titles(db, [room], user.user_id).get(room.id), avatar=service.dm_avatars(db, [room], user.user_id).get(room.id),
    )


def member_in_open_room(db: Session, slug: str, user: TokenPayload) -> Room:
    """The room, for a joined member of a room that is open: what a call or a game is for."""
    room, me = visible(db, slug, user)
    if me is None or me.status != service.JOINED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
    if room.state != service.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, service.ROOM_CLOSED)
    return room
