"""Ephemeral per-room presence (memory only, per process, never stored or logged).

A user is a member of a room while at least one of their sockets is connected to it
(refcount per user id, so several tabs count once). The username is the JWT claim
seen when the first socket connected; it may be stale after a rename.
"""

from datetime import datetime, timezone

MAX_MEMBERS_PER_ROOM = 200
MAX_LIVE_ROOMS = 500
MAX_ROOMS_LISTED = 100
MAX_SOCKETS_PER_USER = 5
MAX_LOBBY_SOCKETS_PER_USER = 2

REASON_ROOM_FULL = "Room is full"
REASON_TOO_MANY_ROOMS = "Too many active rooms"


class Presence:
    def __init__(self) -> None:
        self._names: dict[str, dict[int, str]] = {}
        self._counts: dict[str, dict[int, int]] = {}

    def refusal(self, room: str, user_id: int) -> str | None:
        """Why this user may not open a socket in the room, or None."""
        members = self._names.get(room)
        if members is None:
            return REASON_TOO_MANY_ROOMS if len(self._names) >= MAX_LIVE_ROOMS else None
        if user_id not in members and len(members) >= MAX_MEMBERS_PER_ROOM:
            return REASON_ROOM_FULL
        return None

    def join(self, room: str, user_id: int, username: str) -> bool:
        """Register a socket; True when the user just became a member."""
        names = self._names.setdefault(room, {})
        counts = self._counts.setdefault(room, {})
        first = user_id not in names
        if first:
            names[user_id] = username
        counts[user_id] = counts.get(user_id, 0) + 1
        return first

    def leave(self, room: str, user_id: int) -> bool:
        """Unregister a socket; True when it was the user's last one in the room."""
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

    def members(self, room: str) -> tuple[list[dict], int]:
        names = self._names.get(room, {})
        ordered = sorted(names.items(), key=lambda item: (item[1].lower(), item[0]))
        listed = [{"userId": uid, "username": name} for uid, name in ordered[:MAX_MEMBERS_PER_ROOM]]
        return listed, len(names)

    def rooms(self) -> list[dict]:
        entries = [{"room": room, "users": len(names)} for room, names in self._names.items()]
        entries.sort(key=lambda entry: (-entry["users"], entry["room"]))
        return entries[:MAX_ROOMS_LISTED]


def presence_frame(presence: Presence, room: str) -> dict:
    members, total = presence.members(room)
    return {"type": "presence", "room": room, "members": members, "total": total}


def system_frame(event: str, room: str, user_id: int, username: str) -> dict:
    return {
        "type": "system",
        "event": event,
        "room": room,
        "userId": user_id,
        "username": username,
        "at": datetime.now(timezone.utc).isoformat(),
    }
