"""Ephemeral per-room presence (memory only, per process, never stored or logged).

A user is a member of a room while at least one of their sockets is connected to it
(refcount per user id, so several tabs count once). The username is the JWT claim
seen when the first socket connected; it may be stale after a rename.
"""

from datetime import UTC, datetime

import logging
logger = logging.getLogger(__name__)

MAX_MEMBERS_PER_ROOM = 200
MAX_LIVE_ROOMS = 500
MAX_ROOMS_LISTED = 100
MAX_LOBBY_MEMBERS = 30
MAX_SOCKETS_PER_USER = 5
MAX_LOBBY_SOCKETS_PER_USER = 2

REASON_ROOM_FULL = "Room is full"
REASON_TOO_MANY_ROOMS = "Too many active rooms"


class Presence:
    def __init__(self) -> None:
        try:
            self._names: dict[str, dict[int, str]] = {}
            self._counts: dict[str, dict[int, int]] = {}
            self._remote: dict[str, dict[int, str]] = {}  # the same, in the other copies of the chat (see cluster.py)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    def set_remote(self, rooms: dict[str, dict[int, str]]) -> None:
        try:
            self._remote = rooms
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("set_remote failed")
            raise

    def local_rooms(self) -> dict[str, dict[int, str]]:
        try:
            return {room: dict(names) for room, names in self._names.items()}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("local_rooms failed")
            raise

    def all_presence(self, room: str) -> dict[int, str]:
        try:
            return {**self._remote.get(room, {}), **self._names.get(room, {})}
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("all_presence failed")
            raise

    def room_names(self) -> set[str]:
        try:
            return set(self._names) | set(self._remote)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("room_names failed")
            raise

    def refusal(self, room: str, user_id: int) -> str | None:
        """Why this user may not open a socket in the room, or None."""
        try:
            members = self.all_presence(room) or None
            if members is None:
                return REASON_TOO_MANY_ROOMS if len(self.room_names()) >= MAX_LIVE_ROOMS else None
            if user_id not in members and len(members) >= MAX_MEMBERS_PER_ROOM:
                return REASON_ROOM_FULL
            return None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("refusal failed")
            raise

    def join(self, room: str, user_id: int, username: str) -> bool:
        """Register a socket; True when the user just became a member."""
        try:
            names = self._names.setdefault(room, {})
            counts = self._counts.setdefault(room, {})
            first = user_id not in names
            if first:
                names[user_id] = username
            counts[user_id] = counts.get(user_id, 0) + 1
            return first
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("join failed")
            raise

    def leave(self, room: str, user_id: int) -> bool:
        """Unregister a socket; True when it was the user's last one in the room."""
        try:
            counts = self._counts.get(room)
            if not counts or user_id not in counts:
                return False
            counts[user_id] -= 1
            if counts[user_id] > 0:
                return False
            del counts[user_id]
            del self._names[room][user_id]
            if not counts:
                del self._counts[room]
                del self._names[room]
            return True
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("leave failed")
            raise

    def members(self, room: str) -> tuple[list[dict], int]:
        try:
            names = self.all_presence(room)
            ordered = sorted(names.items(), key=lambda item: (item[1].lower(), item[0]))
            listed = [{"userId": uid, "username": name} for uid, name in ordered[:MAX_MEMBERS_PER_ROOM]]
            return listed, len(names)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("members failed")
            raise

    def rooms(self) -> list[dict]:
        try:
            entries = [
                {
                    "room": room,
                    "users": len(names),
                    "members": sorted(names.values(), key=lambda name: (name.lower(), name))[:MAX_LOBBY_MEMBERS],
                }
                for room, names in ((room, self.all_presence(room)) for room in self.room_names())
                if names
            ]
            entries.sort(key=lambda entry: (-entry["users"], entry["room"]))
            return entries[:MAX_ROOMS_LISTED]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("rooms failed")
            raise


def presence_frame(presence: Presence, room: str) -> dict:
    try:
        members, total = presence.members(room)
        return {"type": "presence", "room": room, "members": members, "total": total}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("presence_frame failed")
        raise


def system_frame(event: str, room: str, user_id: int, username: str) -> dict:
    try:
        return {
            "type": "system",
            "event": event,
            "room": room,
            "userId": user_id,
            "username": username,
            "at": datetime.now(UTC).isoformat(),
        }
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("system_frame failed")
        raise
