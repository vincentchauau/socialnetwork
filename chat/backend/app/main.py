import asyncio
import inspect
import json
import os
import re
import time
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
            if handle is not None:
                await _stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork chat", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    hub = RoomHub()

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

    @app.websocket("/ws/{room}")
    async def chat_socket(websocket: WebSocket, room: str) -> None:
        # Cookies are sent automatically by browsers, so a foreign page could open
        # this socket on a visitor's behalf; browsers always send Origin, so a
        # missing or foreign one is refused.
        if websocket.headers.get("origin") not in _allowed_origins():
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            user = payload_from_cookies(websocket.cookies)
        except AuthError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if not _valid_room(room):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        limiter = MessageRateLimiter(RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
        await hub.join(room, websocket)
        try:
            while True:
                # The token is only checked at connect, so stop listening when it expires.
                remaining = max(user.expires_at - time.time(), 0)
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
                except asyncio.TimeoutError:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                except KeyError:  # binary frame
                    await websocket.send_json({"error": "Only text frames are supported"})
                    continue

                if len(raw) > MAX_FRAME_CHARS:
                    await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                    return
                if not limiter.allow():
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                incoming = _parse_incoming(raw)
                if incoming is None:
                    await websocket.send_json({"error": "Message must be 1-2000 characters"})
                    continue
                saved = await run_in_threadpool(
                    _save_message, app.state.session_factory, room, user, incoming.content
                )
                await hub.broadcast(room, saved.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            hub.leave(room, websocket)

    return app


app = create_app()
