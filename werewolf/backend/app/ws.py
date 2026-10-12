import asyncio
import json
import os
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.engine import (
    CHAT_WOLVES,
    chat_recipients,
    chat_scope,
    cast_vote,
    force_advance,
    GameError,
    submit_action,
)
from app.schemas import (
    ROOM_PATTERN,
    ActionMsg,
    AdvanceMsg,
    ChatMsg,
    VoteMsg,
    client_message_adapter,
)
from app.service import apply_async
from app.store import RoomNotFound
from sn_shared.security import AuthError, TokenPayload, payload_from_cookies

DEFAULT_ALLOWED_ORIGINS = "http://localhost:8080"
MAX_FRAME_CHARS = 8 * 1024
RATE_LIMIT_MESSAGES = 20
RATE_LIMIT_WINDOW_SECONDS = 10.0

router = APIRouter()


def allowed_origins() -> set[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _parse(raw: str) -> ActionMsg | VoteMsg | ChatMsg | AdvanceMsg | None:
    if len(raw) > MAX_FRAME_CHARS:  # never hand an oversized frame to the JSON parser
        return None
    try:
        return client_message_adapter.validate_python(json.loads(raw))
    except (ValueError, ValidationError):
        return None


async def _chat(websocket: WebSocket, room_id: str, user: TokenPayload, message: ChatMsg) -> str | None:
    app = websocket.app
    game = app.state.store.get(room_id)
    scope = chat_scope(game, user.user_id) if game else None
    if game is None or scope is None:
        return "You cannot chat right now"
    payload = {
        "type": "chat",
        "scope": "wolves" if scope == CHAT_WOLVES else "all",
        "username": user.username,  # always from the token
        "content": message.content,
        "sent_at": time.time(),
    }
    await app.state.hub.send_chat(room_id, chat_recipients(game, scope), payload)
    return None


async def _handle(websocket: WebSocket, room_id: str, user: TokenPayload, raw: str) -> str | None:
    """Process one frame; returns an error message for the client, or None."""
    message = _parse(raw)
    if message is None:
        return "Invalid message"
    try:
        if isinstance(message, ChatMsg):
            return await _chat(websocket, room_id, user, message)
        if isinstance(message, ActionMsg):
            await apply_async(websocket.app, room_id, lambda g: submit_action(g, user.user_id, message.target))
        elif isinstance(message, VoteMsg):
            await apply_async(websocket.app, room_id, lambda g: cast_vote(g, user.user_id, message.target))
        else:
            await apply_async(websocket.app, room_id, lambda g: force_advance(g, user.user_id))
    except (GameError, RoomNotFound) as error:
        return "Room not found" if isinstance(error, RoomNotFound) else str(error)
    return None


async def _refuse(websocket: WebSocket) -> None:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@router.websocket("/ws/{room_id}")
async def game_socket(websocket: WebSocket, room_id: str) -> None:
    # Same rules as chat: cookies ride along automatically, so a missing/foreign Origin is refused.
    if websocket.headers.get("origin") not in allowed_origins():
        return await _refuse(websocket)
    try:
        user = payload_from_cookies(websocket.cookies)
    except AuthError:
        return await _refuse(websocket)
    app = websocket.app
    game = app.state.store.get(room_id) if re.fullmatch(ROOM_PATTERN, room_id) else None
    if game is None or game.member(user.user_id) is None:
        return await _refuse(websocket)

    hub = app.state.hub
    if hub.is_full():
        return await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
    limiter = hub.limiter_for(user.user_id, RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
    await hub.join(room_id, websocket, user.user_id)
    try:
        await hub.send_state(room_id, websocket, game, user.user_id)
        while True:
            remaining = max(user.expires_at - time.time(), 0)  # token is only checked at connect
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
            except asyncio.TimeoutError:
                return await _refuse(websocket)
            except KeyError:  # binary frame
                await hub.send_error(websocket, "Only text frames are supported")
                continue
            if len(raw) > MAX_FRAME_CHARS:
                return await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
            if not limiter.allow():
                return await _refuse(websocket)
            error = await _handle(websocket, room_id, user, raw)
            if error is not None:
                await hub.send_error(websocket, error)
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room_id, websocket)
