"""Several copies of the chat behind one gateway: what one copy sees, the others learn through Redis.

Off unless `CHAT_CLUSTER=1` and `REDIS_URL` are set: one copy needs none of this. What is shared:

- frames of a room (messages, joins, cards) and the order to close a person's sockets (a ban): published on one channel, delivered by
  every other copy to ITS sockets;
- who is in which room, and who is online: each copy writes its own picture under a key that expires in `PRESENCE_TTL_SECONDS`
  (a copy that dies leaves nothing behind) and reads the others' ones, so the lists and the counts are of the whole chat;
- "the rooms or the people changed": the other copies refresh what they keep in memory and push their lobby.

What is NOT shared, so these need one copy or a gateway that always sends the same room to the same copy: the Werewolf rooms
(they live in the memory of the copy that made them; a restart puts them back from the database) and the rate limits (each copy
counts for itself). Frames are best effort, like a socket: a copy that misses one catches up from the history.
"""

import asyncio
import json
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)

CHANNEL = "sn:chat:events"
PRESENCE_KEY = "sn:chat:presence:"
PRESENCE_TTL_SECONDS = 15
HEARTBEAT_SECONDS = 5.0
RETRY_SECONDS = 2.0

Handler = Callable[[dict[str, Any]], Awaitable[None]]


def enabled() -> bool:
    return os.environ.get("CHAT_CLUSTER") == "1" and bool(os.environ.get("REDIS_URL")) and not os.environ.get("TESTING")


class Cluster:
    def __init__(self, client: Any, replica: str | None = None) -> None:
        self._client = client
        self.replica = replica or secrets.token_hex(6)
        self._handler: Handler | None = None
        self._snapshot: Callable[[], dict[str, Any]] = lambda: {"rooms": {}, "online": []}
        self._tasks: list[asyncio.Task] = []

    # ---- sending ----
    async def publish(self, event: dict[str, Any]) -> None:
        """Tell the other copies. Never raises: Redis being away must not stop a chat."""
        try:
            await self._client.publish(CHANNEL, json.dumps({**event, "from": self.replica}, ensure_ascii=False, separators=(",", ":")))
        except Exception:  # noqa: BLE001
            log.warning("cluster: could not publish")

    async def write_presence(self) -> None:
        """Write the picture of this copy (who is where, who is online) for the others, and for a while."""
        try:
            await self._client.set(PRESENCE_KEY + self.replica, json.dumps(self._snapshot(), separators=(",", ":")), ex=PRESENCE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            log.warning("cluster: could not write presence")

    async def read_others(self) -> tuple[dict[str, dict[int, str]], set[int]]:
        """The pictures of the other copies, put together: rooms -> {user id: name}, and the ids online."""
        rooms: dict[str, dict[int, str]] = {}
        online: set[int] = set()
        try:
            async for key in self._client.scan_iter(match=PRESENCE_KEY + "*"):
                name = key.decode() if isinstance(key, bytes) else key
                if name == PRESENCE_KEY + self.replica:
                    continue
                raw = await self._client.get(key)
                if raw is None:
                    continue
                picture = json.loads(raw)
                for room, people in picture.get("rooms", {}).items():
                    rooms.setdefault(room, {}).update({int(uid): who for uid, who in people.items()})
                online.update(int(uid) for uid in picture.get("online", []))
        except Exception:  # noqa: BLE001
            log.warning("cluster: could not read presence")
        return rooms, online

    # ---- receiving ----
    async def _listen(self) -> None:
        while True:
            try:
                pubsub = self._client.pubsub()
                await pubsub.subscribe(CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        event = json.loads(message["data"])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(event, dict) and event.get("from") != self.replica and self._handler is not None:
                        try:
                            await self._handler(event)
                        except Exception:  # noqa: BLE001 - one bad event must not end the listening
                            log.exception("cluster: an event failed")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - Redis went away: try again
                log.warning("cluster: lost Redis, retrying")
                await asyncio.sleep(RETRY_SECONDS)

    async def heartbeat(self, refresh: Callable[[], Awaitable[None]]) -> None:
        while True:
            await self.write_presence()
            await refresh()
            await asyncio.sleep(HEARTBEAT_SECONDS)

    async def start(self, handler: Handler, snapshot: Callable[[], dict[str, Any]], refresh: Callable[[], Awaitable[None]]) -> None:
        self._handler, self._snapshot = handler, snapshot
        self._tasks = [asyncio.create_task(self._listen()), asyncio.create_task(self.heartbeat(refresh))]
        await asyncio.sleep(0)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        try:
            await self._client.delete(PRESENCE_KEY + self.replica)
        except Exception:  # noqa: BLE001
            pass
