import asyncio
import inspect
import json
import os
import re
import time
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Path, Query, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db, make_engine
from app.models import Message
from app.lobby import LOBBY_KEY, Lobby
from app.presence import (
    MAX_LOBBY_SOCKETS_PER_USER,
    MAX_SOCKETS_PER_USER,
    Presence,
    presence_frame,
    system_frame,
)
from app.rooms import MessageRateLimiter, RoomHub
from app.schemas import ROOM_PATTERN, IncomingMessage, MessageOut
from sn_shared.deps import get_current_user
from sn_shared.jwtkeys import require_verification_keys
from sn_shared.security import AuthError, TokenPayload, payload_from_cookies

DEFAULT_DATABASE_URL = "sqlite:///./chat.db"
DEFAULT_ALLOWED_ORIGINS = "http://localhost:8080"
HISTORY_DEFAULT_LIMIT = 50
HISTORY_MAX_LIMIT = 200
MAX_FRAME_CHARS = 8 * 1024
RATE_LIMIT_MESSAGES = 20
RATE_LIMIT_WINDOW_SECONDS = 10.0


def _allowed_origins() -> set[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _save_message(factory: sessionmaker, room: str, user: TokenPayload, content: str) -> MessageOut:
    with factory() as session:
        message = Message(room=room, user_id=user.user_id, username=user.username, content=content)
        session.add(message)
        session.commit()
        return MessageOut.model_validate(message)


def _parse_incoming(raw: str) -> IncomingMessage | None:
    """The validated message, or None when the frame is not a valid chat message."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return IncomingMessage.model_validate({"content": str(data.get("content", "")).strip()})
    except (ValueError, ValidationError):
        return None


def _valid_room(room: str) -> bool:
    return re.fullmatch(ROOM_PATTERN, room) is not None


def _start_account_consumer(session_factory: sessionmaker) -> Any:
    """Start center's account-event consumer; None in tests, without Redis or without the library."""
    if os.environ.get("TESTING") or not os.environ.get("REDIS_URL"):
        return None
    try:
        from sn_shared.events import start_account_consumer
    except ImportError:
        return None
    return start_account_consumer("chat", session_factory)


async def _stop_account_consumer(handle: Any) -> None:
    stop = getattr(handle, "stop", None) or getattr(handle, "close", None)
    if stop is None:
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


_TRY_AGAIN_LATER = 1013


class _Expired(Exception):
    pass


def _authorize(websocket: WebSocket) -> TokenPayload | None:
    """The user for a socket handshake, or None. Cookies are sent automatically by
    browsers, so a foreign page could open the socket on a visitor's behalf;
    browsers always send Origin, so a missing or foreign one is refused."""
    if websocket.headers.get("origin") not in _allowed_origins():
        return None
    try:
        return payload_from_cookies(websocket.cookies)
    except AuthError:
        return None


async def _receive(websocket: WebSocket, user: TokenPayload) -> str | None:
    """Next text frame; None for a binary one. The token is only checked at connect,
    so stop listening when it expires (raises _Expired)."""
    remaining = max(user.expires_at - time.time(), 0)
    try:
        return await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
    except asyncio.TimeoutError as error:
        raise _Expired from error
    except KeyError:
        return None


def create_app(database_url: str | None = None) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        handle = _start_account_consumer(application.state.session_factory)
        try:
            yield
        finally:
            await lobby.close()
            if handle is not None:
                await _stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork chat", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    hub = RoomHub()
    presence = Presence()
    lobby = Lobby(presence, RoomHub())
    chat_sockets: Counter[int] = Counter()  # open /ws sockets per user id, over all rooms
    lobby_sockets: Counter[int] = Counter()

    async def announce_leave(room: str, user: TokenPayload) -> None:
        await hub.broadcast(room, system_frame("leave", room, user.user_id, user.username))
        await hub.broadcast(room, presence_frame(presence, room))
        await lobby.notify()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/rooms/{room}/messages", response_model=list[MessageOut])
    def history(
        room: Annotated[str, Path(pattern=ROOM_PATTERN)],
        limit: Annotated[int, Query(ge=1, le=HISTORY_MAX_LIMIT)] = HISTORY_DEFAULT_LIMIT,
        _user: TokenPayload = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> list[Message]:
        latest = db.scalars(
            select(Message).where(Message.room == room).order_by(Message.id.desc()).limit(limit)
        ).all()
        return list(reversed(latest))

    @app.get("/rooms")
    def live_rooms(_user: TokenPayload = Depends(get_current_user)) -> list[dict]:
        return presence.rooms()

    @app.websocket("/ws-lobby")
    async def lobby_socket(websocket: WebSocket) -> None:
        user = _authorize(websocket)
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await websocket.accept()
        if lobby_sockets[user.user_id] >= MAX_LOBBY_SOCKETS_PER_USER:
            await websocket.close(code=_TRY_AGAIN_LATER, reason="Too many lobby connections")
            return
        lobby_sockets[user.user_id] += 1
        lobby.hub.add(LOBBY_KEY, websocket)
        try:
            await websocket.send_json(lobby.frame())
            limiter = MessageRateLimiter(RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
            while True:
                try:
                    raw = await _receive(websocket, user)
                except _Expired:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                if raw is not None and len(raw) > MAX_FRAME_CHARS:
                    await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                    return
                if not limiter.allow():
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                # The lobby is receive-only: client frames are counted and ignored.
        except WebSocketDisconnect:
            pass
        finally:
            lobby.hub.leave(LOBBY_KEY, websocket)
            lobby_sockets[user.user_id] -= 1
            if lobby_sockets[user.user_id] <= 0:
                del lobby_sockets[user.user_id]

    @app.websocket("/ws/{room}")
    async def chat_socket(websocket: WebSocket, room: str) -> None:
        user = _authorize(websocket)
        if user is None or not _valid_room(room):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await websocket.accept()
        refusal = None
        if chat_sockets[user.user_id] >= MAX_SOCKETS_PER_USER:
            refusal = "Too many connections"
        else:
            refusal = presence.refusal(room, user.user_id)
        if refusal is not None:
            await websocket.close(code=_TRY_AGAIN_LATER, reason=refusal)
            return

        limiter = MessageRateLimiter(RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
        chat_sockets[user.user_id] += 1
        first = presence.join(room, user.user_id, user.username)
        hub.add(room, websocket)
        try:
            if first:
                await hub.broadcast(room, system_frame("join", room, user.user_id, user.username))
                await hub.broadcast(room, presence_frame(presence, room))
                await lobby.notify()
            else:
                await websocket.send_json(presence_frame(presence, room))
            while True:
                try:
                    raw = await _receive(websocket, user)
                except _Expired:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                if raw is None:  # binary frame
                    await websocket.send_json({"type": "error", "error": "Only text frames are supported"})
                    continue
                if len(raw) > MAX_FRAME_CHARS:
                    await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                    return
                if not limiter.allow():
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                incoming = _parse_incoming(raw)
                if incoming is None:
                    await websocket.send_json(
                        {"type": "error", "error": "Message must be 1-2000 characters"}
                    )
                    continue
                saved = await run_in_threadpool(
                    _save_message, app.state.session_factory, room, user, incoming.content
                )
                await hub.broadcast(room, {"type": "message", **saved.model_dump(mode="json")})
        except WebSocketDisconnect:
            pass
        finally:
            hub.leave(room, websocket)
            chat_sockets[user.user_id] -= 1
            if chat_sockets[user.user_id] <= 0:
                del chat_sockets[user.user_id]
            if presence.leave(room, user.user_id):
                # Shielded: a cancelled handler must still tell the room the user left.
                await asyncio.shield(announce_leave(room, user))

    return app


app = create_app()
