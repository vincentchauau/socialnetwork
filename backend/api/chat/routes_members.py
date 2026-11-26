"""The members of a room over HTTP: who was in it, and what the owner does about them; the log of the room."""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sn_shared.deps import get_current_user
from sn_shared.directory import Person
from sn_shared.security import TokenPayload
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sn_shared import textsearch
from api.chat import service, virtual_reply
from api.chat.routes_meeting import close_at_livekit, end_all_open
from api.chat.db import get_db
from api.chat.models import Message, Room, RoomMember
from api.chat.social import companions
from api.chat.social import service as social
from api.chat.routes_common import (
    Slug,
    announce,
    disconnect,
    emit,
    new_router,
    owner_of,
    visible,
)
from api.chat.schemas import (
    MemberOut,
    MemberPatch,
)

import logging
logger = logging.getLogger(__name__)

router = new_router()


def member_out(request: Request, room: Room, member: RoomMember, slug: str, show_reason: bool, online: set[int], people: dict[int, Person] | None = None) -> MemberOut:
    try:
        person = (people or {}).get(member.user_id)
        virtual = person is not None and person.kind == "virtual"
        seen = person.view() if person is not None else None
        return MemberOut(
            user_id=member.user_id, username=member.username, role=service.role_of(room, member), status=member.status, muted=member.muted,
            name=seen.display_name if seen else "", avatar=seen.avatar if seen else "",
            online=member.user_id in online or (virtual and member.status == service.JOINED), virtual=virtual,
            status_reason=member.status_reason if show_reason else None,
        )  # fmt: skip
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("member_out failed")
        raise


def people_of(db: Session, user_ids: list[int]) -> dict[int, Person]:
    """The people (rows of `users`) with these ids: who is virtual, and what name and picture each shows."""
    try:
        return {person.user_id: person for person in db.scalars(select(Person).where(Person.user_id.in_(user_ids)))} if user_ids else {}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("people_of failed")
        raise


def listed_statuses(is_owner: bool) -> tuple[str, ...]:
    """Everyone who was ever in the room is listed with their status; a request to join is for the owner only."""
    try:
        return (service.JOINED, service.LEFT, service.KICKED, service.BANNED_STATUS) + ((service.PENDING_STATUS,) if is_owner else ())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("listed_statuses failed")
        raise


@router.get("/rooms/{slug}/members", response_model=list[MemberOut])
def list_members(
    slug: Slug,
    request: Request,
    q: Annotated[str, Query(max_length=32)] = "",
    member_status: Annotated[str, Query(alias="status", pattern="^(joined|pending|left|kicked|banned)?$")] = "",
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    """The people of the room; `q` keeps the ones whose name holds those letters (any accent, any case), `status` the ones in that state."""
    try:
        room, me = visible(db, slug, user)
        is_mod = service.is_owner(room, me)
        query = select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.status.in_(listed_statuses(is_mod)))
        if member_status:
            query = query.where(RoomMember.status == member_status)
        if q.strip():
            query = query.join(Person, Person.user_id == RoomMember.user_id).where(textsearch.folded(Person.username).like(textsearch.pattern(q), escape="\\"))
        members = service.show(db, db.scalars(query.order_by(RoomMember.user_id)).all())
        online = {entry["userId"] for entry in request.app.state.presence.members(slug)[0]}
        people = people_of(db, [m.user_id for m in members])
        return [member_out(request, room, m, slug, is_mod, online, people) for m in members]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_members failed")
        raise


@router.get("/rooms/{slug}/members/{user_id}", response_model=MemberOut)
def read_member(slug: Slug, user_id: int, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> MemberOut:
    """One person of the room, as the list shows them."""
    try:
        room, me = visible(db, slug, user)
        is_mod = service.is_owner(room, me)
        member = service.member_of(db, room.id, user_id)
        if member is None or member.status not in listed_statuses(is_mod):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
        online = {entry["userId"] for entry in request.app.state.presence.members(slug)[0]}
        return member_out(request, room, service.show_one(db, member), slug, is_mod, online, people_of(db, [member.user_id]))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_member failed")
        raise


class AddMemberBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=1, max_length=32)
    user_id: int | None = Field(default=None, ge=1)


@router.post("/rooms/{slug}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(slug: Slug, body: AddMemberBody, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> MemberOut:
    """The owner brings a person in by name (or id): a new member, or one who left or was sent away (the way back). Any other
    member invites: in an open room the person is in, in a room with approval they wait for the owner, and one who was sent away stays out.
    A person who is banned is let in with `PATCH` (lifting the ban), not here. Anybody with an account can be found by name."""
    try:
        if (body.username is None) == (body.user_id is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a username or a user id")
        room, me = visible(db, slug, user)
        if room.kind == "dm":
            raise HTTPException(status.HTTP_409_CONFLICT, "A direct chat has two people")
        if me is None or me.status != service.JOINED:
            raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
        if room.state != service.OPEN and not service.is_owner(room, me):
            raise HTTPException(status.HTTP_409_CONFLICT, service.ROOM_CLOSED)
        invites = not service.is_owner(room, me)
        if body.user_id is not None:
            person = db.get(Person, body.user_id)
        else:
            wanted = (body.username or "").strip().casefold()
            person = db.scalar(select(Person).where(func.lower(Person.username) == wanted))
        if person is None or person.kind == "system":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person")
        member = service.member_of(db, room.id, person.user_id)
        if member is not None and member.status == service.JOINED:
            raise HTTPException(status.HTTP_409_CONFLICT, "Already in the room")
        if member is not None and member.status == service.BANNED_STATUS:
            raise HTTPException(status.HTTP_409_CONFLICT, "The person is banned: lift the ban first")
        if service.joined_members(db, room.id) >= room.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, service.FULL)
        if invites and member is not None and member.status == service.KICKED:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can bring back someone who was sent away")
        if invites and social.blocked_between(db, user.user_id, person.user_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, social.CANNOT_MESSAGE)
        entering = service.PENDING_STATUS if invites and room.join_policy == "approval" else service.JOINED
        if member is None:
            member = service.new_member(db, room, person.user_id, entering, actor_id=user.user_id)
        else:
            service.set_status(db, room, member, entering, actor_id=user.user_id)
        line = service.say(db, room, "joined", person.user_id) if entering == service.JOINED else None
        db.commit()
        if line is not None:
            emit(request, slug, {"type": "member", "event": "join", "user_id": person.user_id, "username": person.username})
            announce(request, slug, [line])
        online = {entry["userId"] for entry in request.app.state.presence.members(slug)[0]}
        return member_out(request, room, service.show_one(db, member), slug, True, online, people_of(db, [member.user_id]))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_member failed")
        raise


@router.patch("/rooms/{slug}/members/{user_id}", response_model=MemberOut)
def change_member(slug: Slug, user_id: int, body: MemberPatch, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> MemberOut:
    try:
        room, me = owner_of(db, slug, user)
        target = service.member_of(db, room.id, user_id)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
        if target.user_id == room.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "The owner cannot be changed")
        changes = body.model_dump(exclude_unset=True)
        new_status = changes.pop("status", None)
        reason = changes.pop("reason", "") or ""
        muted = changes.pop("muted", None)
        if new_status == service.JOINED and target.status not in (service.JOINED, service.PENDING_STATUS, service.BANNED_STATUS):
            raise HTTPException(status.HTTP_409_CONFLICT, "The person has to join again")
        if new_status == service.JOINED and target.status != service.JOINED and service.joined_members(db, room.id) >= room.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, service.FULL)
        lines: list[Message] = []
        target_name = service.show_one(db, target).username
        if new_status is not None and new_status != target.status:
            service.set_status(db, room, target, new_status, actor_id=user.user_id, reason=reason)
            lines.append(service.say(db, room, "banned" if new_status == service.BANNED_STATUS else "joined", user_id))
        if muted is not None:
            service.set_muted(target, muted)
        db.commit()
        if new_status in (service.BANNED_STATUS, service.KICKED):
            names = end_all_open(db, room.id)  # the call ends: those who stay start it again, under a new name the one sent away does not have
            db.commit()
            close_at_livekit(names)
        if new_status == service.BANNED_STATUS:
            disconnect(request, slug, user_id, service.BANNED)
        emit(request, slug, {"type": "member", "event": "change", "user_id": user_id, "username": target_name})
        announce(request, slug, lines)
        online = {entry["userId"] for entry in request.app.state.presence.members(slug)[0]}
        return member_out(request, room, service.show_one(db, target), slug, True, online, people_of(db, [target.user_id]))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("change_member failed")
        raise


@router.delete("/rooms/{slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    slug: Slug, user_id: int, request: Request, reason: Annotated[str, Query(max_length=200)] = "",
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db),
) -> None:
    """Send a member away (status `kicked`: they may join again, unless banned); a pending request is declined the same way."""
    try:
        room, me = owner_of(db, slug, user)
        target = service.member_of(db, room.id, user_id)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
        if target.user_id == room.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "The owner cannot be removed")
        if target.status in (service.LEFT, service.KICKED):
            return  # already away
        lines: list[Message] = []
        target_name = service.show_one(db, target).username
        if target.status == service.PENDING_STATUS:
            service.set_status(db, room, target, service.LEFT, actor_id=user.user_id, reason=reason)
        else:
            service.set_status(db, room, target, service.KICKED, actor_id=user.user_id, reason=reason)
            lines.append(service.say(db, room, "kicked", user_id))
        db.commit()
        if target.status == service.KICKED:
            names = end_all_open(db, room.id)  # the call ends: those who stay start it again, under a new name the one sent away does not have
            db.commit()
            close_at_livekit(names)
        disconnect(request, slug, user_id, "You were removed from the room")
        emit(request, slug, {"type": "member", "event": "leave", "user_id": user_id, "username": target_name})
        announce(request, slug, lines)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("remove_member failed")
        raise


def seat_virtual(request: Request, db: Session, room, slug: str, person: Person, actor_id: int, quiet: bool = False) -> bool:
    """`person` (a virtual one) is in the room: True when they came in now, False when they were in already. Raises 403/409 when they may not."""
    try:
        member = service.member_of(db, room.id, person.user_id)
        if member is not None and member.status == service.JOINED:
            return False
        if member is not None and member.status == service.BANNED_STATUS:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This person is banned from the room")
        if virtual_reply.virtual_count(db, room) >= virtual_reply.MAX_VIRTUAL_PER_ROOM:
            raise HTTPException(status.HTTP_409_CONFLICT, "The room has as many virtual people as allowed")
        if service.joined_members(db, room.id) >= room.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, service.FULL)
        if member is None:
            service.new_member(db, room, person.user_id, service.JOINED, actor_id=actor_id)
        else:
            service.set_status(db, room, member, service.JOINED, actor_id=actor_id)
        line = None if quiet else service.say(db, room, "joined", person.user_id)
        db.commit()
        emit(request, slug, {"type": "member", "event": "join", "user_id": person.user_id, "username": person.username})
        announce(request, slug, [line] if line else [])
        return True
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("seat_virtual failed")
        raise


def member_of_open_room(db: Session, slug: str, user: TokenPayload):
    try:
        room, me = visible(db, slug, user)
        if me is None or me.status != service.JOINED or room.state != service.OPEN or room.kind == "dm":
            raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
        return room
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("member_of_open_room failed")
        raise


def fill_with_virtual(request: Request, db: Session, room, slug: str, actor: TokenPayload, need: int) -> int:
    """The room needs `need` more people (a game wants 5): virtual people at random come in, one line says so. Returns how many came (fewer when
    the pool or the limit of the room is short)."""
    try:
        if need <= 0:
            return 0
        inside = {m.user_id for m in db.scalars(select(RoomMember).where(RoomMember.room_id == room.id))}
        came = 0
        for person in companions.pick(db, actor.user_id, need, inside):
            try:
                if seat_virtual(request, db, room, slug, person, actor.user_id, quiet=True):
                    came += 1
            except HTTPException:
                db.rollback()
                break
        if came:
            line = service.say(db, room, f"virtual_added:{came}", actor.user_id)
            db.commit()
            announce(request, slug, [line])
        return came
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("fill_with_virtual failed")
        raise


class VirtualBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=1, le=virtual_reply.MAX_VIRTUAL_PER_ROOM)


class VirtualOut(BaseModel):
    added: list[dict]
    wanted: int
    why: str | None = None  # why fewer came than were asked, when fewer did


@router.post("/rooms/{slug}/virtual", response_model=VirtualOut)
def add_virtual(slug: Slug, body: VirtualBody, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> VirtualOut:
    """Bring `count` virtual people into the room at once: the ones I already drew who are not in it yet first, then new ones drawn at random
    (they become my companions). Fewer come when the room, the limit of companions or the pool is short; the answer says why. They answer
    what people write there (see `virtual_reply`)."""
    try:
        room = member_of_open_room(db, slug, user)
        left = virtual_reply.MAX_VIRTUAL_PER_ROOM - virtual_reply.virtual_count(db, room)
        wanted = min(body.count, max(left, 0))
        why = None if wanted == body.count else "The room has as many virtual people as allowed"
        chosen: list[Person] = []
        mine = companions.active_ids(db, user.user_id)
        inside = {m.user_id for m in db.scalars(select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.status == service.JOINED))}
        ready = list(db.scalars(select(Person).where(Person.user_id.in_(mine - inside)).order_by(Person.username))) if mine - inside else []
        chosen.extend(ready[:wanted])
        if len(chosen) < wanted:
            try:
                chosen.extend(companions.draw(db, user.user_id, wanted - len(chosen), exclude=inside))
            except social.Refused:
                why = why or "You already have as many companions as allowed"
            else:
                db.commit()
        added = []
        for person in chosen:
            try:
                if seat_virtual(request, db, room, slug, person, user.user_id, quiet=True):
                    added.append({"user_id": person.user_id, "username": person.username, "display_name": person.view().display_name})
            except HTTPException as error:
                db.rollback()
                why = why or str(error.detail)
                break
        if added:  # one line for all of them, not one for each
            line = service.say(db, room, f"virtual_added:{len(added)}", user.user_id)
            db.commit()
            announce(request, slug, [line])
        if len(added) < body.count:
            why = why or "There are no more virtual people to draw"
        return VirtualOut(added=added, wanted=body.count, why=why if len(added) < body.count else None)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_virtual failed")
        raise
