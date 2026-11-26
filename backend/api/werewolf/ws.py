import asyncio
import json
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import TypeAdapter, ValidationError
from sn_shared.security import AuthError, TokenPayload, payload_from_cookies

from api.werewolf.engine import GameError
from api.werewolf.rooms import Room
from api.werewolf.schemas import ROOM_PATTERN, ActionMsg, ChatMsg, ForceMsg
from sn_shared.origin import allowed_origins
from api.werewolf.service import commit

MAX_FRAME_CHARS = 8 * 1024

router = APIRouter()
_client_message = TypeAdapter(ActionMsg | ChatMsg | ForceMsg)


def _parse(raw: str) -> ActionMsg | ChatMsg | ForceMsg | None:
    if len(raw) > MAX_FRAME_CHARS:  # never hand an oversized frame to the JSON parser
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("type") not in ("action", "chat", "force"):
            return None
        return _client_message.validate_python(data)
    except (ValueError, ValidationError):
        return None


async def _chat(websocket: WebSocket, room: Room, user: TokenPayload, message: ChatMsg) -> str | None:
    app = websocket.app
    if not app.state.ww_limits.allow("chat", user.user_id):
        return "Bạn gửi quá nhanh, chờ một chút"
    sent = room.chat(user.user_id, message.text, message.target)
    await app.state.ww_hub.send_chat(room.code, room.chat_recipients(sent), room.chat_payload(sent))
    return None


async def _handle(websocket: WebSocket, room: Room, user: TokenPayload, raw: str) -> str | None:
    """Process one frame; returns an error message for the client, or None."""
    message = _parse(raw)
    if message is None:
        return "Invalid message"
    try:
        if isinstance(message, ChatMsg):
            return await _chat(websocket, room, user, message)
        if isinstance(message, ActionMsg):
            room.submit(user.user_id, message.target, message.kind)
        else:
            room.force(user.user_id)
    except GameError as error:
        return str(error)
    await commit(websocket.app, room)
    return None


async def _refuse(websocket: WebSocket) -> None:
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@router.websocket("/ws/{code}")
async def game_socket(websocket: WebSocket, code: str) -> None:
    # Same rules as chat: cookies ride along automatically, so a missing/foreign Origin is refused.
    if websocket.headers.get("origin") not in allowed_origins():
        return await _refuse(websocket)
    try:
        user = payload_from_cookies(websocket.cookies)
    except AuthError:
        return await _refuse(websocket)
    app = websocket.app
    room = app.state.ww_store.get(code) if re.fullmatch(ROOM_PATTERN, code) else None
    if room is None or room.seat_index(user.user_id) is None:
        return await _refuse(websocket)

    hub = app.state.ww_hub
    if hub.is_full():
        return await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
    await hub.join(room.code, websocket, user.user_id)
    try:
        await hub.send_state(room.code, websocket, room.state_for(user.user_id))
        while True:
            remaining = max(user.expires_at - time.time(), 0)  # token is only checked at connect
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
            except TimeoutError:
                return await _refuse(websocket)
            except KeyError:  # binary frame
                await hub.send_error(websocket, "Only text frames are supported")
                continue
            if len(raw) > MAX_FRAME_CHARS:
                return await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
            if not app.state.ww_limits.allow("ws", user.user_id):
                return await _refuse(websocket)
            error = await _handle(websocket, room, user, raw)
            if error is not None:
                await hub.send_error(websocket, error)
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room.code, websocket)
        room.touch()
