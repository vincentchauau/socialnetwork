import asyncio
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import WebSocket

DEFAULT_SEND_TIMEOUT_SECONDS = 5.0


class RoomHub:
    """Tracks open sockets per room and fans messages out to them (single process)."""

    def __init__(self, send_timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._send_timeout = send_timeout

    async def join(self, room: str, socket: WebSocket) -> None:
        await socket.accept()
        self._rooms[room].add(socket)

    def leave(self, room: str, socket: WebSocket) -> None:
        sockets = self._rooms.get(room)
        if sockets is None:
            return
        sockets.discard(socket)
        if not sockets:
            del self._rooms[room]

    def size(self, room: str) -> int:
        return len(self._rooms.get(room, ()))

    async def broadcast(self, room: str, payload: dict) -> None:
        # Sent concurrently so one slow client cannot hold up the rest of the room.
        sockets = list(self._rooms.get(room, ()))
        await asyncio.gather(*(self._deliver(room, socket, payload) for socket in sockets))

    async def _deliver(self, room: str, socket: WebSocket, payload: dict) -> None:
        try:
            await asyncio.wait_for(socket.send_json(payload), self._send_timeout)
        except Exception:  # slow or dead socket: drop it, keep delivering to the rest
            self.leave(room, socket)


class MessageRateLimiter:
    """Sliding-window limit on how many messages one connection may send."""

    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_events = max_events
        self._window = window_seconds
        self._now = now
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        current = self._now()
        while self._events and self._events[0] <= current - self._window:
            self._events.popleft()
        if len(self._events) >= self._max_events:
            return False
        self._events.append(current)
        return True
