import asyncio
import time
from collections import defaultdict, deque
from typing import Any, Callable

from fastapi import WebSocket, status

from app.engine import Game, view_for

DEFAULT_SEND_TIMEOUT_SECONDS = 5.0


class GameHub:
    """Open sockets per room; each socket only ever receives its own player's redacted view."""

    def __init__(self, send_timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS) -> None:
        self._rooms: dict[str, dict[WebSocket, int]] = defaultdict(dict)
        self._send_timeout = send_timeout

    async def join(self, room: str, socket: WebSocket, user_id: int) -> None:
        await socket.accept()
        self._rooms[room][socket] = user_id

    def leave(self, room: str, socket: WebSocket) -> None:
        sockets = self._rooms.get(room)
        if sockets is None:
            return
        sockets.pop(socket, None)
        if not sockets:
            del self._rooms[room]

    def size(self, room: str) -> int:
        return len(self._rooms.get(room, ()))

    async def send_state(self, room: str, socket: WebSocket, game: Game, user_id: int) -> None:
        await self._deliver(room, socket, {"type": "state", "state": view_for(game, user_id)})

    async def broadcast_state(self, room: str, game: Game) -> None:
        """Send each connected player their own view; evict sockets of players who left."""
        targets = list(self._rooms.get(room, {}).items())
        await asyncio.gather(*(self._push_state(room, s, uid, game) for s, uid in targets))

    async def _push_state(self, room: str, socket: WebSocket, user_id: int, game: Game) -> None:
        if game.member(user_id) is None:
            self.leave(room, socket)
            try:
                await socket.close(code=status.WS_1008_POLICY_VIOLATION)
            except Exception:  # already closed
                pass
            return
        await self.send_state(room, socket, game, user_id)

    async def send_chat(self, room: str, recipients: frozenset[int], payload: dict[str, Any]) -> None:
        targets = [s for s, uid in self._rooms.get(room, {}).items() if uid in recipients]
        await asyncio.gather(*(self._deliver(room, s, payload) for s in targets))

    async def send_error(self, socket: WebSocket, message: str) -> None:
        await socket.send_json({"type": "error", "error": message})

    async def _deliver(self, room: str, socket: WebSocket, payload: dict[str, Any]) -> None:
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
