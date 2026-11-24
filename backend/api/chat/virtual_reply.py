"""The words of virtual people in a room: when a person writes, the virtual people in that room may answer.

The chat asks the `agent` service (a signed call: `sn_shared.servicesig`) what the virtual person would say, then saves it AS that
person with the same rules as anybody's message (a muted or closed room stays silent), and tells the room. Without AGENT_URL
and AGENT_SECRET nothing happens. A virtual person never answers another virtual person, so there are no loops, and at most
`MAX_SPEAKERS` answer one message. One room is answered once at a time: a message written while it is being answered is not.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

from fastapi.concurrency import run_in_threadpool
from sn_shared.directory import Person
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from api.chat import service
from api.chat.agent import service as agent
from api.chat.agent.providers import Line
from api.chat.models import Message, Room, RoomMember
from api.chat.schemas import MessageOut

log = logging.getLogger(__name__)

MAX_SPEAKERS = 2
HISTORY_LINES = 12
LINE_CHARS = 500
TIMEOUT_SECONDS = 25
MAX_VIRTUAL_PER_ROOM = 200  # the capacity of a room: in practice the room's own limit and the size of the pool decide

Broadcast = Callable[[str, dict], Awaitable[None]]
_answering: set[str] = set()


_factory: sessionmaker | None = None


def bind(factory: sessionmaker) -> None:
    """Give the agent the sessions of the chat (set once, when the chat starts)."""
    global _factory
    _factory = factory


def agent_ready() -> bool:
    """The agent answers only when the chat has its sessions."""
    return _factory is not None


def speakers(db: Session, slug: str, author_id: int, rng: random.Random | None = None) -> list[tuple[int, str]]:
    """Who may answer: the virtual people who are joined members of this open room (never the author)."""
    room = service.room_by_slug(db, slug)
    if room is None or room.state != service.OPEN:
        return []
    rows = db.execute(
        select(RoomMember.user_id, Person.username)
        .join(Person, Person.user_id == RoomMember.user_id)
        .where(RoomMember.room_id == room.id, RoomMember.status == service.JOINED, Person.kind == "virtual", RoomMember.user_id != author_id)
        .order_by(RoomMember.user_id)
    ).all()
    chosen = (rng or random.SystemRandom()).sample(rows, min(MAX_SPEAKERS, len(rows)))
    return [(row.user_id, row.username) for row in chosen]


def history(db: Session, slug: str) -> list[dict[str, str]]:
    room = service.room_by_slug(db, slug)
    if room is None:
        return []
    rows = db.scalars(
        select(Message).where(Message.room_id == room.id, Message.kind == "text", Message.deleted_at.is_(None)).order_by(Message.id.desc()).limit(HISTORY_LINES)
    ).all()
    service.show(db, rows)
    return [{"username": m.username[:32], "content": m.content[:LINE_CHARS]} for m in reversed(rows)]


def ask_agent(virtual_id: int, caller_id: int, caller: str, lines: list[dict[str, str]]) -> str | None:
    """The words, or None when the agent cannot give them (down, limited, not configured): the room just stays quiet."""
    answer = ask_agent_counted(virtual_id, caller_id, caller, lines)
    return answer[0] if answer else None


def usage_line(name: str, tokens_in: int, tokens_out: int, ms: int) -> str:
    """The content of the line of `system` that tells what an answer cost: `ai_usage:<in>:<out>:<ms>:<who answered>` (the interface words it)."""
    return f"ai_usage:{tokens_in}:{tokens_out}:{ms}:{name}"


def ask_agent_counted(virtual_id: int, caller_id: int, caller: str, lines: list[dict[str, str]]) -> tuple[str, tuple[int, int, int]] | None:
    """Like `ask_agent`, with (tokens sent, tokens written, milliseconds the whole request took, the call to the agent included)."""
    started = time.monotonic()
    if _factory is None or not lines:
        return None
    history = [Line(item["username"], item["content"]) for item in lines]
    with _factory() as db:
        answer = agent.reply(db, virtual_id, caller_id, caller, history)
    if answer is None or not answer.text.strip():
        return None
    return answer.text.strip(), (answer.usage.tokens_in, answer.usage.tokens_out, round((time.monotonic() - started) * 1000))


def tell_usage(factory: sessionmaker, slug: str, name: str, counted: tuple[int, int, int]) -> MessageOut | None:
    """Write the cost of an answer in the room as a line of `system`; None when the room is gone."""
    with factory() as db:
        room = service.room_by_slug(db, slug)
        if room is None:
            return None
        line = service.say_text(db, room, usage_line(name, *counted))
        db.commit()
        db.refresh(line)
        return MessageOut.model_validate(line)


def save(factory: sessionmaker, slug: str, virtual_id: int, username: str, text: str) -> MessageOut | None:
    """Save the words as the virtual person, by the rules of the room; None when the room does not take them."""
    with factory() as db:
        room = service.room_by_slug(db, slug)
        if room is None or service.posting_problem(room, service.member_of(db, room.id, virtual_id)) is not None:
            return None
        message = Message(room_id=room.id, user_id=virtual_id, content=text[:2000])
        db.add(message)
        db.commit()
        return MessageOut.model_validate(service.show_one(db, message))


async def reply_in_room(factory: sessionmaker, broadcast: Broadcast, slug: str, author: SimpleNamespace | object) -> None:
    """Called after a person's message was saved and told to the room."""
    if not agent_ready() or slug in _answering:
        return
    _answering.add(slug)
    try:
        def plan() -> list[tuple[int, str]]:
            with factory() as db:
                return speakers(db, slug, author.user_id)  # type: ignore[attr-defined]

        for virtual_id, username in await run_in_threadpool(plan):
            def lines() -> list[dict[str, str]]:
                with factory() as db:
                    return history(db, slug)

            answer = await run_in_threadpool(
                lambda: ask_agent_counted(virtual_id, author.user_id, author.username, lines())  # type: ignore[attr-defined]
            )
            if answer is None:
                continue
            text, counted = answer
            saved = await run_in_threadpool(save, factory, slug, virtual_id, username, text)
            if saved is not None:
                await broadcast(slug, saved.frame())
                told = await run_in_threadpool(tell_usage, factory, slug, username, counted)
                if told is not None:
                    await broadcast(slug, told.frame())
    except Exception:  # noqa: BLE001 - a failing reply must never reach the person who wrote
        log.exception("a virtual reply failed")
    finally:
        _answering.discard(slug)


def member_names(db: Session, room: Room) -> list[tuple[str, str]]:
    """(name, kind) of everyone in the room, in the order they came: a virtual person by their display name (kind `virtual`), a person by their
    username (kind `human`)."""
    rows = db.execute(
        select(Person.username, Person.name, Person.kind)
        .select_from(RoomMember)
        .join(Person, Person.user_id == RoomMember.user_id)
        .where(RoomMember.room_id == room.id, RoomMember.status == service.JOINED)
        .order_by(RoomMember.user_id)
    ).all()
    return [(((display or username) if kind == "virtual" else username).strip(), "virtual" if kind == "virtual" else "human") for username, display, kind in rows]


def virtual_count(db: Session, room: Room) -> int:
    return len(
        db.scalars(
            select(RoomMember.user_id)
            .join(Person, Person.user_id == RoomMember.user_id)
            .where(RoomMember.room_id == room.id, RoomMember.status == service.JOINED, Person.kind == "virtual")
        ).all()
    )


def spawn(tasks: set[asyncio.Task], coroutine: Awaitable[None]) -> None:
    """Run in the background and keep the task alive until it is done."""
    task = asyncio.ensure_future(coroutine)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
