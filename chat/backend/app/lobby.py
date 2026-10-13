import asyncio
import time
from collections.abc import Awaitable, Callable

from app.presence import Presence
from app.rooms import RoomHub

LOBBY_KEY = "lobby"
MIN_PUSH_INTERVAL_SECONDS = 0.5  # at most 2 room-list pushes per second


class Lobby:
    """Sockets watching the room list; pushes are coalesced (leading edge + one trailing)."""

    def __init__(
        self,
        presence: Presence,
        hub: RoomHub,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        interval: float = MIN_PUSH_INTERVAL_SECONDS,
    ) -> None:
        self.hub = hub
        self._presence = presence
        self._clock = clock
        self._sleep = sleep
        self._interval = interval
        self._last_push = float("-inf")
        self._pending: asyncio.Task | None = None

    def frame(self) -> dict:
        return {"type": "rooms", "rooms": self._presence.rooms()}

    async def notify(self) -> None:
        """Call after any change of the set of rooms or their counts."""
        if self._pending is not None:
            return  # a trailing push is already scheduled and will carry the latest state
        wait = self._last_push + self._interval - self._clock()
        if wait <= 0:
            await self._push()
        else:
            self._pending = asyncio.create_task(self._delayed(wait))

    async def _delayed(self, wait: float) -> None:
        try:
            await self._sleep(wait)
        finally:
            self._pending = None
        await self._push()

    async def _push(self) -> None:
        self._last_push = self._clock()
        await self.hub.broadcast(LOBBY_KEY, self.frame())

    async def close(self) -> None:
        task = self._pending
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
