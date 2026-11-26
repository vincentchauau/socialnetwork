"""Rooms over HTTP: make, list, change, delete, join, leave, hand over, read marks, a chat of two, people."""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sn_shared.deps import GROUP_ADMIN, get_current_user
from sn_shared import directory
from sn_shared.directory import Person as SocialPerson
from sn_shared.directory import Person as DirectoryPerson
from sn_shared.security import TokenPayload
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sn_shared import textsearch
from api.chat import service, werewolf_remote
from api.chat.db import get_db
from api.chat.models import Message, Room, RoomMember
from api.chat.routes_common import (
    LIST_DEFAULT_LIMIT,
    LIST_MAX_LIMIT,
    Slug,
    announce,
    changed,
    disconnect,
    emit,
    new_router,
    one_out,
    owner_of,
    room_out,
    visible,
)
from api.chat.schemas import (
    DmCreate,
    MessageHit,
    ReadBody,
    RoomCreate,
    RoomOut,
    RoomUpdate,
    SearchHit,
    TransferBody,
)
from api.chat.social import companions
from api.chat.social import service as social_service

router = new_router()


@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(body: RoomCreate, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    owned = db.scalar(select(func.count()).select_from(Room).where(Room.user_id == user.user_id, Room.kind == "chat", Room.state == service.OPEN)) or 0
    total = db.scalar(select(func.count()).select_from(Room).where(Room.state == service.OPEN)) or 0
    if owned >= service.MAX_ROOMS_PER_OWNER or total >= service.MAX_ROOMS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many rooms")
    if body.slug and service.room_by_slug(db, body.slug) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That address is already used")
    slug = body.slug or service.free_slug(db, service.slug_from(body.title))
    fields = body.model_dump(exclude={"slug"})
    room = Room(slug=slug, kind="chat", user_id=user.user_id, **fields)
    db.add(room)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That address is already used") from None
    me = service.new_member(db, room, user.user_id, service.JOINED)  # every room has an owner (`Room.user_id`), whoever it is open to
    db.commit()
    changed(request, db)
    return one_out(request, db, room, me, user)


@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(
    request: Request,
    scope: Annotated[str, Query(pattern="^(public|mine|past|requests)$")] = "public",
    q: Annotated[str, Query(max_length=80)] = "",
    category: Annotated[str, Query(max_length=32)] = "",
    limit: Annotated[int, Query(ge=1, le=LIST_MAX_LIMIT)] = LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RoomOut]:
    counts = (
        select(RoomMember.room_id.label("room_id"), func.count().label("n"))
        .where(RoomMember.status == service.JOINED)
        .group_by(RoomMember.room_id)
        .subquery()
    )
    query = select(Room, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.room_id == Room.id)
    if scope == "mine":  # (a request to write to me waits under `requests`, not here)
        mine = select(RoomMember.room_id).where(
            RoomMember.user_id == user.user_id,
            or_(RoomMember.status == service.JOINED, (RoomMember.status == service.PENDING_STATUS) & (Room.kind != "dm")),
        )
        query = query.where(Room.id.in_(mine), Room.state != service.DELETED)
    elif scope == "requests":  # people who ask to write to me, and I have not answered
        asked = select(RoomMember.room_id).where(RoomMember.user_id == user.user_id, RoomMember.status == service.PENDING_STATUS)
        query = query.where(Room.id.in_(asked), Room.kind == "dm", Room.state != service.DELETED)
    elif scope == "past":  # where I was (left or sent away; a room I made and deleted) and may read again
        went = select(RoomMember.room_id).where(RoomMember.user_id == user.user_id, RoomMember.status.in_((service.LEFT, service.KICKED)), RoomMember.hidden_at.is_(None))
        query = query.where(or_(Room.id.in_(went) & (Room.state != service.DELETED), (Room.user_id == user.user_id) & (Room.state == service.DELETED)))
    else:
        query = query.where(Room.visibility == "public", Room.kind == "chat", Room.state == service.OPEN)
    like = service.like_pattern(q) if q.strip() else None
    if like is not None:
        # Any of the words of the room, one of its members, or something said in it (a room that is not listed is not searched).
        member_has = (
            select(RoomMember.room_id)
            .join(DirectoryPerson, DirectoryPerson.user_id == RoomMember.user_id)
            .where(RoomMember.room_id == Room.id, RoomMember.status == service.JOINED, textsearch.folded(DirectoryPerson.username).like(like, escape="\\"))
            .exists()
        )
        said = select(Message.id).where(Message.room_id == Room.id, Message.deleted_at.is_(None), Message.kind == "text", textsearch.folded(Message.content).like(like, escape="\\")).exists()
        query = query.where(or_(*[textsearch.folded(column).like(like, escape="\\") for column in (Room.title, Room.slug, Room.category)], member_has, said))
    if category.strip():
        query = query.where(textsearch.folded(Room.category) == textsearch.fold(category.strip()))
    if scope == "public":
        order = [func.coalesce(counts.c.n, 0).desc(), Room.id.desc()]
    else:  # the conversation that had a message last comes first
        newest = select(func.max(Message.id)).where(Message.room_id == Room.id).correlate(Room).scalar_subquery()
        order = [func.coalesce(newest, 0).desc(), Room.id.desc()]
    rows = db.execute(query.order_by(*order).limit(limit).offset(offset)).all()
    ids = [room.id for room, _ in rows]
    mine_by_room = {m.room_id: m for m in db.scalars(select(RoomMember).where(RoomMember.user_id == user.user_id, RoomMember.room_id.in_(ids)))} if ids else {}
    unread = service.unread_counts(db, user.user_id, ids)
    hits = service.search_hits(db, [room for room, _ in rows], q) if like is not None else {}
    last = service.last_messages(db, ids) if scope != "public" else {}
    owners = service.owner_names(db, [room for room, _ in rows])
    titles = service.dm_titles(db, [room for room, _ in rows], user.user_id)
    pictures = service.dm_avatars(db, [room for room, _ in rows], user.user_id)
    return [room_out(request, room, n, mine_by_room.get(room.id), unread.get(room.id, 0), hit(hits.get(room.id)), last.get(room.id), owners.get(room.id, ""), titles.get(room.id), pictures.get(room.id)) for room, n in rows]


def hit(found: dict | None) -> SearchHit | None:
    if found is None:
        return None
    message = found["message"]
    return SearchHit(fields=found["fields"], members=found["members"], message=MessageHit(**message) if message else None)


@router.get("/rooms/{slug}", response_model=RoomOut)
def read_room(slug: Slug, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    room, me = visible(db, slug, user)
    return one_out(request, db, room, me, user)


@router.patch("/rooms/{slug}", response_model=RoomOut)
def update_room(slug: Slug, body: RoomUpdate, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    room, me = owner_of(db, slug, user)
    changes = body.model_dump(exclude_unset=True)
    if room.kind == "dm" and set(changes) - {"state"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A direct chat cannot be changed")
    if changes.get("capacity") is not None and changes["capacity"] < service.joined_members(db, room.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "The room already has more members than that")
    visibility = changes.get("visibility", room.visibility)
    policy = changes.get("join_policy", room.join_policy)
    if visibility == "private" and policy == "open":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A private room is joined with an invitation or approval, not openly")
    previous_policy = room.join_policy
    state, lines = changes.pop("state", None), []
    for field, value in changes.items():
        setattr(room, field, value)
    if state is not None:
        before = room.state
        service.set_state(db, room, state, actor_id=user.user_id)
        if before != room.state:
            lines.append(service.say(db, room, "closed" if state == service.CLOSED else "reopened", user.user_id))
    if policy == "open" and previous_policy == "approval" and room.kind == "chat":
        for member in service.admit_pending(db, room):
            lines.append(service.say(db, room, "joined", member.user_id))
    db.commit()
    changed(request, db)
    emit(request, room.slug, {"type": "room", "room": room.slug})
    announce(request, slug, lines)
    return one_out(request, db, room, me, user)


def drop_game_routes_rooms(request: Request, code: str | None) -> None:
    """The game of a deleted room goes with it (it would keep its players' seats, which count toward their limit): the game is asked to drop it."""
    if code:
        try:
            werewolf_remote.drop_game(request.app, code)
        except HTTPException:
            pass  # the game is gone or unreachable: the room is deleted all the same


@router.delete("/rooms/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def remove_room(
    slug: Slug, request: Request, permanent: bool = False,
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db),
) -> None:
    """Delete the room (hidden, kept). With `permanent` a room that is already deleted goes for good, messages and all.
    Only the room's owner deletes it; an admin may delete any room (to act on a breach)."""
    if user.group == GROUP_ADMIN:
        room = service.room_by_slug(db, slug)
        if room is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, service.NOT_FOUND)
    else:
        room, _ = owner_of(db, slug, user)
    game_code = service.game_code(room) if room.kind == "chat" else None
    if permanent:
        if room.state != service.DELETED:
            raise HTTPException(status.HTTP_409_CONFLICT, "Delete the room first")
        service.purge_room(db, room)
        db.commit()
        changed(request, db)
        drop_game_routes_rooms(request, game_code)
        return
    members = [m.user_id for m in db.scalars(select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.status == service.JOINED))]
    service.set_state(db, room, service.DELETED, actor_id=user.user_id)  # hidden, with everything in it kept
    db.commit()
    changed(request, db)
    drop_game_routes_rooms(request, game_code)
    for user_id in members:
        disconnect(request, slug, user_id, "Room deleted")


@router.post("/rooms/{slug}/join", response_model=RoomOut)
def join_room(slug: Slug, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    room = service.room_by_slug(db, slug)
    me = service.member_of(db, room.id, user.user_id) if room else None
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, service.NOT_FOUND)
    granted, refusal = service.can_join(room, me)
    if refusal is not None:
        code = status.HTTP_404_NOT_FOUND if refusal == service.NOT_FOUND else status.HTTP_403_FORBIDDEN
        if refusal == service.ROOM_CLOSED:
            code = status.HTTP_409_CONFLICT
        raise HTTPException(code, refusal)
    if me is None or me.status in (service.LEFT, service.KICKED):  # coming back changes the status of the same row
        if granted == service.JOINED and service.joined_members(db, room.id) >= room.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, service.FULL)
        if me is None:
            me = service.new_member(db, room, user.user_id, granted)
        else:
            service.set_status(db, room, me, granted, actor_id=user.user_id)
        if granted == service.JOINED and room.kind == "chat" and not service.has_owner(db, room):
            room.user_id = user.user_id  # a room nobody owns goes to the next person who comes in
        line = service.say(db, room, "joined", user.user_id) if granted == service.JOINED else None
        db.commit()
        if line is not None:
            emit(request, slug, {"type": "member", "event": "join", "user_id": user.user_id, "username": user.username})
            announce(request, slug, [line])
    changed(request, db)
    return one_out(request, db, room, me, user)


@router.post("/rooms/{slug}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_room(slug: Slug, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    room, me = visible(db, slug, user)
    if me is None or me.status not in (service.JOINED, service.PENDING_STATUS):
        return  # nothing to leave (a ban stays: leaving must not undo it)
    lines: list[Message] = []
    if service.is_owner(room, me) and room.kind == "chat":
        if service.transfer_target(db, room, user.user_id) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, service.HAND_OVER_FIRST)  # the owner chooses the next one: Set owner
        service.set_state(db, room, service.CLOSED, actor_id=user.user_id, reason="the last member left")
    elif service.is_owner(room, me):
        service.set_state(db, room, service.CLOSED, actor_id=user.user_id, reason="a person left the chat")
    service.set_status(db, room, me, service.LEFT, actor_id=user.user_id)
    lines.append(service.say(db, room, "left", user.user_id))
    db.commit()
    changed(request, db)
    emit(request, slug, {"type": "member", "event": "leave", "user_id": user.user_id, "username": user.username})
    announce(request, slug, lines)
    disconnect(request, slug, user.user_id, "You left the room")


@router.post("/rooms/{slug}/hide", status_code=status.HTTP_204_NO_CONTENT)
def hide_room(slug: Slug, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Take a room I left (or was sent out of) off my list of past rooms. The room, its messages and my membership stay."""
    room, me = visible(db, slug, user)
    if me is None or me.status not in (service.LEFT, service.KICKED):
        raise HTTPException(status.HTTP_409_CONFLICT, "Leave the room first")
    me.hidden_at = service.now()
    db.commit()


@router.post("/rooms/{slug}/transfer", response_model=RoomOut)
def transfer(slug: Slug, body: TransferBody, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    room, me = owner_of(db, slug, user)
    target = service.member_of(db, room.id, body.user_id)
    if target is None or target.status != service.JOINED or target.user_id == user.user_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose another active member")
    room.user_id = target.user_id
    line = service.say(db, room, "transferred", target.user_id)
    db.commit()
    emit(request, slug, {"type": "room", "room": slug})
    announce(request, slug, [line])
    return one_out(request, db, room, me, user)


@router.post("/rooms/{slug}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(slug: Slug, body: ReadBody, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    room, me = visible(db, slug, user)
    if me is None or me.status != service.JOINED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
    if body.message_id > (me.last_read_message_id or 0):
        me.last_read_message_id = body.message_id
        db.commit()


@router.post("/dm", response_model=RoomOut)
def open_dm(body: DmCreate, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    """A private room of two. With someone I met in a room, or a friend, it is open at once; with anyone else who is one of the
    people (a stranger) it is a request: they are `pending` until they say yes, and may read what I wrote (three messages at most)."""
    if body.user_id == user.user_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose someone else")
    someone = db.scalar(select(RoomMember).where(RoomMember.user_id == body.user_id, RoomMember.status == service.JOINED).limit(1))
    other_id, other_name = (someone.user_id, directory.name_of(db, someone.user_id)) if someone is not None else (None, None)
    if other_id is None:
        person = social_service.friend_person(db, user.user_id, body.user_id) or db.get(SocialPerson, body.user_id)
        if person is None or person.kind == "system":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
        other_id, other_name = person.user_id, person.username
    if social_service.blocked_between(db, user.user_id, other_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, social_service.CANNOT_MESSAGE)  # whoever blocked whom: the same words
    other_person = db.get(SocialPerson, other_id)
    acquainted = (
        (other_person is not None and other_person.kind == "virtual")  # nobody to answer a request: a virtual person is written to at once, as a friend is
        or social_service.friend_person(db, user.user_id, other_id) is not None
        or service.share_a_room(db, user.user_id, other_id)
        or companions.is_companion(db, user.user_id, other_id)
    )
    room = service.room_by_slug(db, service.dm_slug(user.user_id, other_id))  # one chat of two for a pair: its address is made of the two ids
    if room is None:
        if not acquainted and service.requests_waiting(db, user.user_id) >= service.MAX_DM_REQUESTS_WAITING:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests")
        room = Room(
            slug=service.dm_slug(user.user_id, other_id), kind="dm", title=f"{user.username} & {other_name}",
            user_id=user.user_id, visibility="private", join_policy="invite", capacity=2,
        )  # fmt: skip
        db.add(room)
        db.flush()
        service.new_member(db, room, user.user_id, service.JOINED)
        service.new_member(db, room, other_id, service.JOINED if acquainted else service.PENDING_STATUS, actor_id=user.user_id)
        if not acquainted:
            social_service.notify(db, other_id, "message_request", social_service.actor_of(db, user.user_id, user.username), slug=room.slug)
        db.commit()
    else:  # a chat that was left or closed is opened again, for both: unless the other said no and we are strangers
        theirs = service.member_of(db, room.id, other_id)
        if theirs is not None and theirs.status == service.LEFT and theirs.status_reason == service.DECLINED and not acquainted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, social_service.CANNOT_MESSAGE)
        if room.state != service.OPEN:
            service.set_state(db, room, service.OPEN, actor_id=user.user_id)
        for person_id in (user.user_id, other_id):
            member = service.member_of(db, room.id, person_id)
            if member is None:
                service.new_member(db, room, person_id, service.JOINED, actor_id=user.user_id)
            elif member.status in (service.LEFT, service.KICKED) or (member.status == service.PENDING_STATUS and acquainted):
                service.set_status(db, room, member, service.JOINED, actor_id=user.user_id)
        db.commit()
    me = service.member_of(db, room.id, user.user_id)
    return one_out(request, db, room, me, user)


def asked_of_me(db: Session, slug: str, user: TokenPayload) -> tuple[Room, RoomMember]:
    """The private chat that someone asked me for and I have not answered."""
    room, me = visible(db, slug, user)
    if room.kind != "dm" or me is None or me.status != service.PENDING_STATUS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, service.NOT_FOUND)
    return room, me


@router.post("/rooms/{slug}/accept", response_model=RoomOut)
def accept_request(slug: Slug, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> RoomOut:
    """Say yes to a private chat that someone asked for: it is a chat of two from now on."""
    room, me = asked_of_me(db, slug, user)
    if social_service.blocked_between(db, user.user_id, room.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, social_service.CANNOT_MESSAGE)
    service.set_status(db, room, me, service.JOINED, actor_id=user.user_id)
    social_service.notify(db, room.user_id, "message_accepted", social_service.actor_of(db, user.user_id, user.username), slug=room.slug)
    db.commit()
    emit(request, slug, {"type": "member", "event": "join", "user_id": user.user_id, "username": user.username})
    return one_out(request, db, room, me, user)


@router.post("/rooms/{slug}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_request(slug: Slug, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Say no: the asker is not told, and cannot ask again (unless they become friends)."""
    room, me = asked_of_me(db, slug, user)
    service.set_status(db, room, me, service.LEFT, actor_id=user.user_id, reason=service.DECLINED)
    db.commit()

