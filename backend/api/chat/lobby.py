import asyncio
import time
from collections.abc import Awaitable, Callable

from api.chat.presence import Presence
from api.chat.rooms import RoomHub

import logging
logger = logging.getLogger(__name__)

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
        allow: Callable[[str], bool] = lambda room: True,
        extra: Callable[[], dict] = lambda: {},
    ) -> None:
        try:
            self.hub = hub
            self._presence = presence
            self._clock = clock
            self._sleep = sleep
            self._interval = interval
            self._allow = allow  # which rooms the list may name: the public ones only
            self._extra = extra  # what else a frame says: a version that moves when rooms or the people online change
            self._last_push = float("-inf")
            self._pending: asyncio.Task | None = None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def frame(self) -> dict:
        try:
            rooms = [entry for entry in self._presence.rooms() if self._allow(entry["room"])]
            return {"type": "rooms", "rooms": rooms, **self._extra()}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("frame failed")
            raise

    async def notify(self) -> None:
        """Call after any change of the set of rooms or their counts."""
        try:
            if self._pending is not None:
                return  # a trailing push is already scheduled and will carry the latest state
            wait = self._last_push + self._interval - self._clock()
            if wait <= 0:
                await self.push_lobby()
            else:
                self._pending = asyncio.create_task(self.delayed(wait))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("notify failed")
            raise

    async def delayed(self, wait: float) -> None:
        try:
            await self._sleep(wait)
        finally:
            self._pending = None
        await self.push_lobby()

    async def push_lobby(self) -> None:
        try:
            self._last_push = self._clock()
            await self.hub.broadcast(LOBBY_KEY, self.frame())
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("push_lobby failed")
            raise

    async def close(self) -> None:
        try:
            task = self._pending
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("close failed")
            raise
