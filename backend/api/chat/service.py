"""The rules of rooms and their members, apart from HTTP and sockets so both can use them."""

import hashlib
import hmac
import os
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from sn_shared import directory, textsearch
from sn_shared.directory import Person
from api.chat.models import CARD_PREFIX, MUTED_REASON, SYSTEM_USER_ID, Message, Room, RoomMember

# A member's status: the row stays for good, only this changes. A muted member is `joined` with the reason `muted`.
PENDING_STATUS, JOINED, LEFT, KICKED, BANNED_STATUS = "pending", "joined", "left", "kicked", "banned"
# A room's state: it is never removed either.
OPEN, CLOSED, DELETED = "open", "closed", "deleted"
READERS = (JOINED, LEFT, KICKED)  # whoever was in a room may read it again, but only a joined member writes
MAX_ROOMS_PER_OWNER = 20
MAX_ROOMS = 5000
SLUG_BASE_MAX = 24
DM_PREFIX = "dm-"  # the slug of a chat of two is `dm-<low id>-<high id>`: nobody else may take such an address

# What a client is told when a rule says no (the interface translates these).
NOT_FOUND = "Room not found"
NOT_A_MEMBER = "You are not a member of this room"
PENDING = "Waiting for approval"
BANNED = "You are banned from this room"
ROOM_CLOSED = "Room is not open"
MUTED = "You are muted"
FULL = "Room is full"
INVITE_ONLY = "This room is by invitation"
HAND_OVER_FIRST = "Hand the room over to someone before you leave"
DECLINED = "declined"  # the reason kept on the membership of someone who said no to a private chat

MAX_REQUEST_MESSAGES = 3  # what a stranger may send before the other has said yes to a private chat
MAX_DM_REQUESTS_WAITING = 20  # private chats a person started that nobody has answered yet
SNIPPET = 80


def now() -> datetime:
    return datetime.now(UTC)


def is_owner(room: Room, member: RoomMember | None) -> bool:
    """The owner of a room is `Room.user_id`; there are no other powers (no moderators)."""
    return member is not None and member.status == JOINED and member.user_id == room.user_id


def role_of(room: Room, member: RoomMember) -> str:
    return "owner" if member.user_id == room.user_id else "member"


def member_of(db: Session, room_id: int, user_id: int) -> RoomMember | None:
    return db.get(RoomMember, (room_id, user_id))


def room_by_slug(db: Session, slug: str) -> Room | None:
    return db.scalar(select(Room).where(Room.slug == slug))


def joined_members(db: Session, room_id: int) -> int:
    return db.scalar(select(func.count()).select_from(RoomMember).where(RoomMember.room_id == room_id, RoomMember.status == JOINED)) or 0


def public_slugs(db: Session) -> set[str]:
    """The rooms the lobby may name: public chat rooms that were not deleted."""
    return set(db.scalars(select(Room.slug).where(Room.visibility == "public", Room.kind == "chat", Room.state != DELETED)))


# ---- the game of a room and what is said once in a while ---------------------------------------------------------

ANNOUNCE_AGAIN_AFTER = timedelta(minutes=15)  # a call or a game that goes on is said once, not at every click
GAME_CODE_LETTERS = "ABCDEFGHIJKLMNPQRSTUVWXYZ"
GAME_CODE_LENGTH = 5  # the length of a werewolf room code
_ANNOUNCED: dict[tuple[int, str], datetime] = {}  # (room, what) -> when it was said (in memory: a restart may say it once more)


def secret_service() -> bytes:
    secret = os.environ.get("WEREWOLF_SECRET") or os.environ.get("JWT_SECRET")
    if not secret and os.environ.get("APP_ENV") == "production":
        raise RuntimeError("WEREWOLF_SECRET or JWT_SECRET must be set in production")
    return (secret or "dev").encode()


def game_code(room: Room) -> str:
    """The code of the Werewolf game of a room: worked out from its address and a secret, so nothing is stored (the same every time)."""
    digest = hmac.new(secret_service(), f"game:{room.slug}".encode(), hashlib.sha256).digest()
    return "".join(GAME_CODE_LETTERS[digest[i] % len(GAME_CODE_LETTERS)] for i in range(GAME_CODE_LENGTH))


def room_by_game_code(db: Session, code: str) -> Room | None:
    """The room whose game has this code: the codes of the rooms are worked out (a few thousand rooms at most), none is stored."""
    for room in db.scalars(select(Room).where(Room.kind == "chat", Room.state != DELETED)):
        if hmac.compare_digest(game_code(room), code):
            return room
    return None


def said_recently(room: Room, key: str) -> bool:
    last = _ANNOUNCED.get((room.id, key))
    return last is not None and now() - last < ANNOUNCE_AGAIN_AFTER


def announce_once(db: Session, room: Room, key: str, what: str, user_id: int) -> Message | None:
    """Say in the conversation that someone started a game, unless it was said a moment ago."""
    if said_recently(room, key):
        return None
    _ANNOUNCED[(room.id, key)] = now()
    return say(db, room, what, user_id)


def announce_text_once(db: Session, room: Room, key: str, content: str) -> Message | None:
    """Like `announce_once`, as a line of `system` that names nobody (`meeting:both`)."""
    if said_recently(room, key):
        return None
    _ANNOUNCED[(room.id, key)] = now()
    return say_text(db, room, content)


def slug_from(title: str) -> str:
    folded = unicodedata.normalize("NFKD", title.replace("đ", "d").replace("Đ", "D"))
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")[:SLUG_BASE_MAX].strip("-")
    base = base if len(base) >= 3 else "room"
    return f"room-{base}" if base.startswith(DM_PREFIX) else base  # (the address of a chat of two is not for a room)


def free_slug(db: Session, wanted: str) -> str:
    """`wanted`, or `wanted-2`, `wanted-3`… (kept within 32 characters) until one is not taken."""
    slug, n = wanted, 1
    while room_by_slug(db, slug) is not None:
        n += 1
        tail = f"-{n}"
        slug = wanted[: 32 - len(tail)] + tail
    return slug


def dm_slug(a: int, b: int) -> str:
    low, high = sorted((a, b))
    return f"{DM_PREFIX}{low}-{high}"


def can_join(room: Room, member: RoomMember | None) -> tuple[str | None, str | None]:
    """What joining does: (the status the member gets, None) or (None, the reason it is refused)."""
    if room.state == DELETED:
        return None, NOT_FOUND
    if member is not None and member.status == BANNED_STATUS:
        return None, BANNED
    if member is not None and member.status in (JOINED, PENDING_STATUS):
        return member.status, None
    if room.state == CLOSED:
        return None, ROOM_CLOSED
    if room.visibility == "private" or room.join_policy == "invite":
        return None, NOT_FOUND if room.visibility == "private" else INVITE_ONLY
    return (PENDING_STATUS if room.join_policy == "approval" else JOINED), None


def posting_problem(room: Room, member: RoomMember | None) -> str | None:
    """Why this member may not post in the room right now, or None."""
    if member is None:
        return NOT_A_MEMBER
    if member.status == PENDING_STATUS:
        return PENDING
    if member.status == BANNED_STATUS:
        return BANNED
    if member.status != JOINED:
        return NOT_A_MEMBER
    if room.state != OPEN:
        return ROOM_CLOSED
    if member.muted:
        return MUTED
    return None


def unread_counts(db: Session, user_id: int, room_ids: list[int]) -> dict[int, int]:
    """Messages after each room's read marker, not by me and not deleted."""
    if not room_ids:
        return {}
    last_read = {m.room_id: m.last_read_message_id or 0 for m in db.scalars(
        select(RoomMember).where(RoomMember.user_id == user_id, RoomMember.room_id.in_(room_ids), RoomMember.status == JOINED)
    )}
    if not last_read:
        return {}
    rows = db.execute(
        select(Message.room_id, Message.id).where(
            Message.room_id.in_(list(last_read)), Message.user_id != user_id, Message.deleted_at.is_(None), Message.user_id != SYSTEM_USER_ID
        )
    ).all()
    counts: dict[int, int] = {}
    for room_id, message_id in rows:
        if message_id > last_read[room_id]:
            counts[room_id] = counts.get(room_id, 0) + 1
    return counts


def transfer_target(db: Session, room: Room, leaving_user_id: int) -> RoomMember | None:
    """The person who could own a room whose owner goes: the joined member with the lowest id, a real person before a virtual one."""
    virtual = select(Person.user_id).where(Person.kind == "virtual")
    return db.scalars(
        select(RoomMember)
        .where(RoomMember.room_id == room.id, RoomMember.status == JOINED, RoomMember.user_id != leaving_user_id)
        .order_by(case((RoomMember.user_id.in_(virtual), 1), else_=0), RoomMember.user_id)
    ).first()


def has_owner(db: Session, room: Room) -> bool:
    return db.scalar(select(RoomMember.user_id).where(RoomMember.room_id == room.id, RoomMember.user_id == room.user_id, RoomMember.status == JOINED)) is not None


def admit_pending(db: Session, room: Room) -> list[RoomMember]:
    """A room that is open now has no one to wait for: the requests that were waiting come in, as far as there is room. Returns who came in."""
    waiting = db.scalars(select(RoomMember).where(RoomMember.room_id == room.id, RoomMember.status == PENDING_STATUS).order_by(RoomMember.user_id)).all()
    free = max(room.capacity - joined_members(db, room.id), 0)
    let_in = list(waiting[:free])
    for member in let_in:
        set_status(db, room, member, JOINED)
    return let_in


SYSTEM_USERNAME = "system"


def owner_names(db: Session, rooms: list[Room]) -> dict[int, str]:
    """The name of the owner of each room (`Room.user_id`)."""
    if not rooms:
        return {}
    found = directory.names(db, [room.user_id for room in rooms])
    return {room.id: found[room.user_id] for room in rooms}


def dm_titles(db: Session, rooms: list[Room], viewer_id: int) -> dict[int, str]:
    """What each chat of two is called to the one who reads it: the name of the other person (the title kept on the room has both)."""
    ids = [room.id for room in rooms if room.kind == "dm"]
    if not ids:
        return {}
    rows = db.execute(select(RoomMember.room_id, RoomMember.user_id).where(RoomMember.room_id.in_(ids), RoomMember.user_id != viewer_id)).all()
    found = directory.names(db, [user_id for _, user_id in rows])
    return {room_id: found[user_id] for room_id, user_id in rows}


def dm_avatars(db: Session, rooms: list[Room], viewer_id: int) -> dict[int, str]:
    """The picture of a chat of two, to the one who reads it: the one of the other person, as their profile lets the viewer see it."""
    ids = [room.id for room in rooms if room.kind == "dm"]
    if not ids:
        return {}
    rows = db.execute(select(RoomMember.room_id, RoomMember.user_id).where(RoomMember.room_id.in_(ids), RoomMember.user_id != viewer_id)).all()
    people = {person.user_id: person for person in db.scalars(select(Person).where(Person.user_id.in_([user_id for _, user_id in rows])))}
    return {room_id: people[user_id].view().avatar for room_id, user_id in rows if user_id in people}


PERSON_OF_LINE = re.compile(r"<(\d+)>$")  # a system line ends with the id of who it is about (`<` and `>` are not in a username)


def show(db: Session, rows):
    """Puts `username` on messages (or members) so a response schema can read it: one lookup for all of them. `system` is not in `users`."""
    rows = directory.attach_names(db, rows)
    spoken = [row for row in rows if row.user_id == SYSTEM_USER_ID]
    named = directory.names(db, [int(found) for row in spoken for found in PERSON_OF_LINE.findall(row.content or "")])
    for row in spoken:
        row.username = SYSTEM_USERNAME
        row.shown_content = PERSON_OF_LINE.sub(lambda match: named[int(match.group(1))], row.content or "")  # (not a column: never stored)
    return rows


def show_one(db: Session, row):
    return show(db, [row])[0]


def say(db: Session, room: Room, kind: str, user_id: int) -> Message:
    """A line of the conversation about a change, said by `system`: the content is what happened and to whom (`kicked:<12>`,
    `virtual_added:4:<7>`: the id of the person, which `show` turns into their name, so a rename shows in the old lines too;
    older lines hold the name itself, `kicked:bob`); the interface words it."""
    message = Message(room_id=room.id, user_id=SYSTEM_USER_ID, content=f"{kind}:<{user_id}>")
    message.username = SYSTEM_USERNAME  # (not columns: what the schema of a message reads)
    message.shown_content = f"{kind}:{directory.name_of(db, user_id)}"
    db.add(message)
    return message


def say_text(db: Session, room: Room, content: str) -> Message:
    """A line of `system` about something that is not a person (`game_over:WOLF:4`); the interface words it."""
    message = Message(room_id=room.id, user_id=SYSTEM_USER_ID, content=content)
    message.username = SYSTEM_USERNAME  # (not a column: what the schema of a message reads)
    message.shown_content = content
    db.add(message)
    return message


def say_card(db: Session, room: Room, card: dict) -> Message:
    """A card said by `system` (the result of a game): shown to everybody, with nothing to answer."""
    from api.chat import assistant  # (assistant imports this module)

    message = Message(room_id=room.id, user_id=SYSTEM_USER_ID, content=assistant.encode(card))
    message.username = SYSTEM_USERNAME  # (not a column: what the schema of a message reads)
    message.shown_content = message.content
    db.add(message)
    return message


def new_member(db: Session, room: Room, user_id: int, status: str, actor_id: int | None = None) -> RoomMember:
    member = RoomMember(room_id=room.id, user_id=user_id, status=status)
    db.add(member)
    return member


EVENT_OF = {  # (status before, status after) -> what happened; else the new status
    (PENDING_STATUS, JOINED): "approved",
    (PENDING_STATUS, LEFT): "declined",
    (BANNED_STATUS, JOINED): "unbanned",
}


def set_status(db: Session, room: Room, member: RoomMember, status: str, actor_id: int | None = None, reason: str = "") -> None:
    """Move a member to another status. The row stays; the reason is kept (a ban, a refusal), and coming back clears it (and any mute)."""
    if member.status == status:
        return
    member.status = status
    if status in (JOINED, PENDING_STATUS):
        member.status_reason = ""
        member.hidden_at = None
    else:  # left (a refusal of a request to write says so: DECLINED) | kicked | banned
        member.status_reason = reason[:200]


def set_muted(member: RoomMember, muted: bool) -> None:
    """A joined member who may read and not write (or may write again)."""
    if member.status == JOINED:
        member.status_reason = MUTED_REASON if muted else ""


def set_state(db: Session, room: Room, state: str, actor_id: int | None = None, reason: str = "") -> None:
    """Close, reopen, delete or restore a room: only its state changes, with everything in it kept."""
    room.state = state


def purge_room(db: Session, room: Room) -> None:
    """Remove a room for good, with its messages and members. Only the owner may ask, and only for a room already deleted."""
    db.query(Message).filter(Message.room_id == room.id).update({Message.reply_to_id: None}, synchronize_session=False)
    db.query(Message).filter(Message.room_id == room.id).delete(synchronize_session=False)
    db.query(RoomMember).filter(RoomMember.room_id == room.id).delete(synchronize_session=False)
    db.delete(room)


SEARCH_FIELDS = ("title", "slug", "category")
HIT_MEMBERS = 3
SNIPPET_CHARS = 120


like_pattern = textsearch.pattern  # `%words%` for a LIKE (escape `\\`), folded: no case, no accents, a % or _ is not a wildcard


def snippet(content: str, words: str) -> str:
    """The part of a message around the words, cut to a line."""
    text = " ".join(content.split())
    folded = textsearch.fold(text)
    at = folded.find(textsearch.fold(words.strip())) if len(folded) == len(text) else -1  # (folding that changes the length: no pointing)
    if len(text) <= SNIPPET_CHARS or at < 0:
        return text[:SNIPPET_CHARS] + ("…" if len(text) > SNIPPET_CHARS else "")
    start = max(0, at - SNIPPET_CHARS // 3)
    end = min(len(text), start + SNIPPET_CHARS)
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


def search_hits(db: Session, rooms: list[Room], words: str) -> dict[int, dict]:
    """For each room of a search result: which of its fields hold the words, which members' names do, and the latest message."""
    needle = textsearch.fold(words.strip())
    ids = [room.id for room in rooms]
    hits = {
        room.id: {"fields": [name for name in SEARCH_FIELDS if needle in textsearch.fold(getattr(room, name) or "")], "members": [], "message": None}
        for room in rooms
    }
    if not ids:
        return hits
    like = like_pattern(words)
    for room_id, username in db.execute(
        select(RoomMember.room_id, Person.username)
        .join(Person, Person.user_id == RoomMember.user_id)
        .where(RoomMember.room_id.in_(ids), RoomMember.status == JOINED, textsearch.folded(Person.username).like(like, escape="\\"))
        .order_by(RoomMember.user_id)
    ):
        if len(hits[room_id]["members"]) < HIT_MEMBERS:
            hits[room_id]["members"].append(username)
    found = db.scalars(
        select(Message)
        .where(Message.room_id.in_(ids), Message.deleted_at.is_(None), Message.kind == "text", textsearch.folded(Message.content).like(like, escape="\\"))
        .order_by(Message.id.desc())
        .limit(len(ids) * 5)
    ).all()
    for message in show(db, found):
        if hits[message.room_id]["message"] is None:
            hits[message.room_id]["message"] = {"id": message.id, "username": message.username, "content": snippet(message.content, words)}
    return hits


# ---- the inbox ---------------------------------------------------------------------------------------------------


def last_messages(db: Session, room_ids: list[int]) -> dict[int, dict]:
    """The newest message of each room that has one (not deleted): who said it, a line of it, and when."""
    if not room_ids:
        return {}
    newest = (
        select(func.max(Message.id)).where(Message.room_id.in_(room_ids), Message.deleted_at.is_(None)).group_by(Message.room_id)
    )
    found: dict[int, dict] = {}
    for message in show(db, db.scalars(select(Message).where(Message.id.in_(newest)))):
        text = " ".join(message.content.removeprefix(CARD_PREFIX).split())
        found[message.room_id] = {
            "username": message.username, "kind": message.kind, "at": message.created_at,
            "content": text[:SNIPPET] + ("…" if len(text) > SNIPPET else ""),
        }  # fmt: skip
    return found


def requests_waiting(db: Session, user_id: int) -> int:
    """Private chats `user_id` started that the other person has not answered yet: how many requests a person may have out at once."""
    return db.scalar(
        select(func.count()).select_from(Room).where(
            Room.kind == "dm", Room.user_id == user_id, Room.state != DELETED,
            Room.id.in_(select(RoomMember.room_id).where(RoomMember.status == PENDING_STATUS, RoomMember.user_id != user_id)),
        )
    ) or 0


def share_a_room(db: Session, a: int, b: int) -> bool:
    """Both are joined members of one room: how people who met in a room may write to each other at once."""
    mine = select(RoomMember.room_id).where(RoomMember.user_id == a, RoomMember.status == JOINED)
    return db.scalar(select(RoomMember.room_id).where(RoomMember.user_id == b, RoomMember.status == JOINED, RoomMember.room_id.in_(mine)).limit(1)) is not None


def waiting_for_answer(db: Session, room: Room, user_id: int) -> bool:
    """A private chat where the other person has not answered the request yet, and `user_id` has used up what a stranger may send."""
    if room.kind != "dm":
        return False
    waiting = db.scalar(select(RoomMember.user_id).where(RoomMember.room_id == room.id, RoomMember.user_id != user_id, RoomMember.status == PENDING_STATUS))
    if waiting is None:
        return False
    sent = db.scalar(select(func.count()).select_from(Message).where(Message.room_id == room.id, Message.user_id == user_id, Message.kind == "text")) or 0
    return sent >= MAX_REQUEST_MESSAGES
