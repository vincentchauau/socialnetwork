"""In-memory room registry (single process). Bounded: max rooms, max rooms per user, idle/finished reaping.

Not thread-safe on purpose: every mutation runs on the event loop (the routes are `async def`), so no
await ever sits between a read and the write that depends on it.
"""

import random
import time
from collections.abc import Callable

from api.werewolf.engine import MAX_PLAYERS, MAX_TIMER, MIN_PLAYERS, MIN_TIMER, Ability, Faction, validate_roles
from api.werewolf.rooms import (
    CODE_ALPHABET,
    CODE_LENGTH,
    CapacityError,
    GameRecord,
    Room,
    RoomError,
    RoomNotFound,
    Seat,
    TooManyRooms,
    pick_names,
    random_room_title,
)

MAX_ROOMS = 200
MAX_ROOMS_PER_USER = 20  # rooms (lobby, running or finished-but-not-reaped) a user holds a seat in
IDLE_ROOM_SECONDS = 30 * 60  # no activity and no open socket -> reaped
FINISHED_ROOM_SECONDS = 5 * 60  # same, for finished games
MAX_PERSIST_ATTEMPTS = 5  # bounded retries for storing a result

__all__ = ["MAX_ROOMS", "MAX_ROOMS_PER_USER", "RoomNotFound", "RoomStore"]


def _never_connected(_code: str) -> bool:
    return False


def bot_seat_names(count: int, username: str, preferred: list[tuple[str, str]] | None) -> list[tuple[str, str]]:
    """(name, origin) of the seats the machine plays: the `preferred` ones first (the other people of a chat room: virtual ones and
    people who have not sat yet), then random fillers (origin empty)."""
    taken = {username.casefold()}
    names: list[tuple[str, str]] = []
    for name, kind in preferred or []:
        name = name.strip()
        if name and name.casefold() not in taken and len(names) < count:
            taken.add(name.casefold())
            names.append((name, kind))
    fillers = pick_names(count - len(names), taken | {n.casefold() for n, _ in names})
    return names + [(name, "") for name in fillers]


class RoomStore:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        is_connected: Callable[[str], bool] = _never_connected,
        rng: random.Random | None = None,
        max_rooms: int = MAX_ROOMS,
        max_rooms_per_user: int = MAX_ROOMS_PER_USER,
    ) -> None:
        self.clock = clock
        self.is_connected = is_connected  # does a room have open sockets? (set by the app)
        self.rng = rng or random.SystemRandom()
        self.max_rooms = max_rooms
        self.max_rooms_per_user = max_rooms_per_user
        self._rooms: dict[str, Room] = {}
        self._orphans: list[GameRecord] = []  # results of rooms deleted before they were stored
        self.removed: set[str] = set()  # codes of deleted rooms whose saved copy is still to be forgotten

    # ---- lookup ----
    def get(self, code: str) -> Room | None:
        return self._rooms.get(code.upper())

    def require(self, code: str) -> Room:
        room = self.get(code)
        if room is None:
            raise RoomNotFound(code)
        return room

    def codes(self) -> set[str]:
        return set(self._rooms)

    def adopt(self, room: Room) -> None:
        """Put back a room that was saved before a restart."""
        self._rooms[room.code] = room
        self.removed.discard(room.code)

    def all(self) -> list[Room]:
        return list(self._rooms.values())

    def __len__(self) -> int:
        return len(self._rooms)

    def rooms_of(self, user_id: int) -> list[Room]:
        return [r for r in self._rooms.values() if r.seat_index(user_id) is not None]

    def open_lobbies(self, limit: int = 50) -> list[Room]:
        self.reap()
        lobbies = [r for r in self._rooms.values() if r.listed and r.game is None and r.open_seats > 0]
        return sorted(lobbies, key=lambda r: -r.last_active)[:limit]

    # ---- limits ----
    def require_free_slot(self, user_id: int) -> None:
        if len(self.rooms_of(user_id)) >= self.max_rooms_per_user:
            raise TooManyRooms(f"Bạn đang ở trong {self.max_rooms_per_user} phòng, hãy rời bớt một phòng")

    def _new_code(self) -> str:
        while True:
            code = "".join(self.rng.choices(CODE_ALPHABET, k=CODE_LENGTH))
            if code not in self._rooms:
                return code

    # ---- lifecycle ----
    def create(
        self,
        host_id: int,
        username: str,
        *,
        roles: list[tuple[Faction, Ability]] | None = None,
        count: int | None = None,
        title: str | None = None,
        code: str | None = None,
        timer: int = 0,
        events: bool = True,
        dead_talk: bool = True,
        listed: bool = True,
        bot_names: list[tuple[str, str]] | None = None,
    ) -> Room:
        """New room; the host takes seat 1. `roles` = per-seat setup (len = seat count), else `count` random seats."""
        if timer and not MIN_TIMER <= timer <= MAX_TIMER:
            raise RoomError(f"Đồng hồ phải từ {MIN_TIMER} đến {MAX_TIMER} giây")
        if roles is not None:
            validate_roles(roles)
        total = len(roles) if roles is not None else (count or MIN_PLAYERS)
        if not MIN_PLAYERS <= total <= MAX_PLAYERS:
            raise RoomError(f"Số người chơi phải từ {MIN_PLAYERS} đến {MAX_PLAYERS}")
        self.require_free_slot(host_id)
        self.reap()
        if len(self._rooms) >= self.max_rooms:
            raise CapacityError("Server đã đạt số phòng tối đa, thử lại sau")
        code = code.upper() if code else self._new_code()
        if code in self._rooms:
            raise RoomError(f"Mã phòng {code} đã có người dùng, hãy chọn mã khác")
        names = bot_seat_names(total - 1, username, bot_names)
        seats = [Seat(username, host_id)] + [Seat(name, origin=origin) for name, origin in names]
        if roles is not None:
            for seat, (faction, ability) in zip(seats, roles):
                seat.faction, seat.ability = faction, ability
        room = Room(code, host_id, title or random_room_title(self.rng), seats, self.clock, listed=listed,
                    timer=timer, events=events, dead_talk=dead_talk)
        self._rooms[code] = room
        return room

    def join(self, code: str, user_id: int, username: str) -> Room:
        room = self.require(code)
        if room.seat_index(user_id) is None:
            self.require_free_slot(user_id)
        room.join(user_id, username, self.rng)
        return room

    def leave(self, code: str, user_id: int) -> Room | None:
        """Remove the user; returns the room, or None when it was deleted (no human left)."""
        room = self.require(code)
        if room.leave(user_id):
            self.delete(code)
            return None
        return room

    def delete(self, code: str) -> None:
        room = self._rooms.pop(code.upper(), None)
        if room is not None:
            self.removed.add(room.code)
            room.collect_result()  # a game that just ended must not lose its result with the room
            self._orphans.extend(r for r in room.records if not r.saved)

    # ---- reaper / persistence ----
    def _is_expired(self, room: Room, now: float) -> bool:
        limit = FINISHED_ROOM_SECONDS if room.finished else IDLE_ROOM_SECONDS
        return now - room.last_active >= limit and not self.is_connected(room.code)

    def reap(self) -> list[str]:
        """Delete idle/finished rooms nobody is connected to; returns the removed codes."""
        now = self.clock()
        expired = [c for c, r in self._rooms.items() if self._is_expired(r, now)]
        for code in expired:
            self.delete(code)
        return expired

    def unsaved_results(self) -> list[GameRecord]:
        """Results still to store (records past the retry cap are dropped)."""
        pending: list[GameRecord] = []
        for room in self._rooms.values():
            room.records[:] = [r for r in room.records if not r.saved and r.attempts < MAX_PERSIST_ATTEMPTS]
            pending.extend(r for r in room.records if not r.inflight)
        self._orphans = [r for r in self._orphans if not r.saved and r.attempts < MAX_PERSIST_ATTEMPTS]
        pending.extend(r for r in self._orphans if not r.inflight)
        return pending
