import asyncio
import json
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket, status

import logging
logger = logging.getLogger(__name__)

DEFAULT_SEND_TIMEOUT_SECONDS = 5.0
MAX_CONNECTIONS = 500  # global cap on open sockets; further connects are refused with 1013


def dumps(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("dumps failed")
        raise


class GameHub:
    """Open sockets per room. Each socket only ever receives its own user's view of the room.

    A state change costs one `state_for` + one JSON encoding per connected user (not per socket), and a socket
    whose last state frame is byte-identical is skipped.
    """

    def __init__(
        self,
        send_timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS,
        max_connections: int = MAX_CONNECTIONS,
    ) -> None:
        try:
            self._rooms: dict[str, dict[WebSocket, int]] = defaultdict(dict)
            self._last: dict[WebSocket, str] = {}  # last state frame sent per socket
            self._send_timeout = send_timeout
            self._max_connections = max_connections
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def total(self) -> int:
        try:
            return sum(len(sockets) for sockets in self._rooms.values())
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("total failed")
            raise

    def is_full(self) -> bool:
        try:
            return self.total() >= self._max_connections
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("is_full failed")
            raise

    def size(self, room: str) -> int:
        try:
            return len(self._rooms.get(room, ()))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("size failed")
            raise

    def users(self, room: str) -> set[int]:
        try:
            return set(self._rooms.get(room, {}).values())
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("users failed")
            raise

    async def join(self, room: str, socket: WebSocket, user_id: int) -> None:
        """Accept the socket. At most one socket per (room, user): a newer one replaces the older,
        which is closed with 1008 (the newest tab wins, so a stale tab cannot hold the seat)."""
        try:
            await socket.accept()
            sockets = self._rooms[room]
            displaced = [s for s, uid in sockets.items() if uid == user_id]
            for old in displaced:
                del sockets[old]
                self._last.pop(old, None)
            sockets[socket] = user_id
            for old in displaced:
                await self.close_hub(old)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("join failed")
            raise

    def leave(self, room: str, socket: WebSocket) -> None:
        try:
            self._last.pop(socket, None)
            sockets = self._rooms.get(room)
            if sockets is None:
                return
            sockets.pop(socket, None)
            if not sockets:
                del self._rooms[room]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("leave failed")
            raise

    @staticmethod
    async def close_hub(socket: WebSocket, code: int = status.WS_1008_POLICY_VIOLATION) -> None:
        try:
            await socket.close(code=code)
        except Exception:  # already closed
            pass

    async def send_state(self, room: str, socket: WebSocket, state: dict[str, Any]) -> None:
        try:
            await self.push_state(room, socket, dumps({"type": "state", "state": state}))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("send_state failed")
            raise

    async def broadcast(self, room: str, state_for: Callable[[int], dict[str, Any] | None]) -> None:
        """Send every connected user their own state; users without a seat any more are disconnected."""
        try:
            by_user: dict[int, list[WebSocket]] = defaultdict(list)
            for socket, user_id in list(self._rooms.get(room, {}).items()):
                by_user[user_id].append(socket)
            sends = []
            for user_id, sockets in by_user.items():
                state = state_for(user_id)
                if state is None:
                    for socket in sockets:
                        self.leave(room, socket)
                        sends.append(self.close_hub(socket))
                    continue
                frame = dumps({"type": "state", "state": state})
                sends.extend(self.push_state(room, socket, frame) for socket in sockets)
            await asyncio.gather(*sends)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("broadcast failed")
            raise

    async def push_state(self, room: str, socket: WebSocket, frame: str) -> None:
        try:
            if self._last.get(socket) == frame:
                return
            if await self.deliver(room, socket, frame):
                self._last[socket] = frame
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("push_state failed")
            raise

    async def send_chat(self, room: str, recipients: list[int], message: dict[str, Any]) -> None:
        """A chat message goes only to the users allowed to read it (not a whole-state push)."""
        try:
            wanted = set(recipients)
            frame = dumps({"type": "chat", "message": message})
            targets = [s for s, uid in self._rooms.get(room, {}).items() if uid in wanted]
            await asyncio.gather(*(self.deliver(room, s, frame) for s in targets))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("send_chat failed")
            raise

    async def send_error(self, socket: WebSocket, message: str) -> None:
        try:
            await socket.send_text(dumps({"type": "error", "error": message}))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("send_error failed")
            raise

    async def deliver(self, room: str, socket: WebSocket, frame: str) -> bool:
        try:
            await asyncio.wait_for(socket.send_text(frame), self._send_timeout)
        except Exception:  # slow or dead socket: drop it, keep delivering to the rest
            self.leave(room, socket)
            return False
        return True

    async def close_room(self, room: str) -> None:
        try:
            for socket in list(self._rooms.get(room, {})):
                self.leave(room, socket)
                await self.close_hub(socket, status.WS_1001_GOING_AWAY)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("close_room failed")
            raise
