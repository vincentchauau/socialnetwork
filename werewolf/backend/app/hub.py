import asyncio
import time
from collections import defaultdict, deque
from typing import Any, Callable

from fastapi import WebSocket, status

from app.engine import Game, view_for

DEFAULT_SEND_TIMEOUT_SECONDS = 5.0
MAX_CONNECTIONS = 500  # global cap on open sockets; further connects are refused with 1013


class GameHub:
    """Open sockets per room; each socket only ever receives its own player's redacted view."""

    def __init__(
        self,
        send_timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS,
        max_connections: int = MAX_CONNECTIONS,
    ) -> None:
        self._rooms: dict[str, dict[WebSocket, int]] = defaultdict(dict)
        self._send_timeout = send_timeout
        self._max_connections = max_connections
        self._limiters: dict[int, "MessageRateLimiter"] = {}

    def total(self) -> int:
        return sum(len(sockets) for sockets in self._rooms.values())

    def is_full(self) -> bool:
        return self.total() >= self._max_connections

    def limiter_for(self, user_id: int, max_events: int, window: float) -> "MessageRateLimiter":
        """One shared limiter per user, so extra connections do not multiply the allowance."""
        self._prune_limiters()
        limiter = self._limiters.get(user_id)
        if limiter is None:
            limiter = self._limiters[user_id] = MessageRateLimiter(max_events, window)
        return limiter

    def _prune_limiters(self) -> None:
        connected = {uid for sockets in self._rooms.values() for uid in sockets.values()}
        for user_id in [u for u, lim in self._limiters.items() if u not in connected and lim.idle()]:
            del self._limiters[user_id]

    async def join(self, room: str, socket: WebSocket, user_id: int) -> None:
        """Accept the socket. At most one socket per (room, user): a newer one replaces the older,
        which is closed with 1008 (the newest tab wins, so a stale tab cannot hold the seat)."""
        await socket.accept()
        sockets = self._rooms[room]
        displaced = [s for s, uid in sockets.items() if uid == user_id]
        for old in displaced:
            del sockets[old]
        sockets[socket] = user_id
        for old in displaced:
            try:
                await old.close(code=status.WS_1008_POLICY_VIOLATION)
            except Exception:  # already closed
                pass

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

    def idle(self) -> bool:
        current = self._now()
        return not self._events or self._events[-1] <= current - self._window

    def allow(self) -> bool:
        current = self._now()
        while self._events and self._events[0] <= current - self._window:
            self._events.popleft()
        if len(self._events) >= self._max_events:
            return False
        self._events.append(current)
        return True
