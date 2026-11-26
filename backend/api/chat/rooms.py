import asyncio
from collections import defaultdict

from fastapi import WebSocket

import logging
logger = logging.getLogger(__name__)

DEFAULT_SEND_TIMEOUT_SECONDS = 5.0


class RoomHub:
    """Tracks open sockets per room and fans messages out to them (single process)."""

    def __init__(self, send_timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS) -> None:
        try:
            self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
            self._send_timeout = send_timeout
            self.cluster = None  # set when there are several copies of the chat: a frame is also told to the others
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    async def join(self, room: str, socket: WebSocket) -> None:
        try:
            await socket.accept()
            self._rooms[room].add(socket)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("join failed")
            raise

    def add(self, room: str, socket: WebSocket) -> None:
        """Register an already accepted socket."""
        try:
            self._rooms[room].add(socket)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("add failed")
            raise

    def leave(self, room: str, socket: WebSocket) -> None:
        try:
            sockets = self._rooms.get(room)
            if sockets is None:
                return
            sockets.discard(socket)
            if not sockets:
                del self._rooms[room]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("leave failed")
            raise

    def size(self, room: str) -> int:
        try:
            return len(self._rooms.get(room, ()))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("size failed")
            raise

    async def broadcast(self, room: str, payload: dict) -> None:
        try:
            await self.broadcast_local(room, payload)
            if self.cluster is not None:
                await self.cluster.publish({"t": "frame", "room": room, "payload": payload})
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("broadcast failed")
            raise

    async def broadcast_local(self, room: str, payload: dict) -> None:
        """To the sockets of this copy only."""
        # Sent concurrently so one slow client cannot hold up the rest of the room.
        try:
            sockets = list(self._rooms.get(room, ()))
            await asyncio.gather(*(self.deliver(room, socket, payload) for socket in sockets))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("broadcast_local failed")
            raise

    async def deliver(self, room: str, socket: WebSocket, payload: dict) -> None:
        try:
            await asyncio.wait_for(socket.send_json(payload), self._send_timeout)
        except Exception:  # slow or dead socket: drop it, keep delivering to the rest
            self.leave(room, socket)


