"""In-memory room registry (single process, like chat's RoomHub). Thread-safe."""

import random
import secrets
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable

from app.engine import Game, GameError, Phase, add_player, new_game

MAX_ROOMS = 200
ROOM_ID_BYTES = 6  # token_urlsafe(6) -> 8 chars from [A-Za-z0-9_-]
IDLE_ROOM_SECONDS = 30 * 60  # no activity and no open socket -> reaped
FINISHED_ROOM_SECONDS = 5 * 60  # same, for finished games
MAX_PERSIST_ATTEMPTS = 5  # bounded retries for saving a finished game's result


class RoomNotFound(LookupError):
    pass


@dataclass
class _Room:
    game: Game
    last_activity: float
    persisted: bool = False
    persist_attempts: int = 0


@dataclass(frozen=True)
class UpdateResult:
    game: Game
    finished_now: bool  # True while a finished game still has to be saved (bounded retries)
    deleted: bool


def _never_connected(_room_id: str) -> bool:
    return False


class RoomStore:
    def __init__(
        self,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        is_connected: Callable[[str], bool] = _never_connected,
    ) -> None:
        self._rooms: dict[str, _Room] = {}
        self._lock = threading.Lock()
        self._clock = clock
        self.is_connected = is_connected  # does a room have open sockets? (set by the app)
        # Role shuffles decide who is a wolf: use the OS CSPRNG unless a test injects a seeded one.
        self.rng = rng or random.SystemRandom()

    def _active_room_of(self, user_id: int) -> str | None:
        for room_id, room in self._rooms.items():
            if room.game.phase is not Phase.FINISHED and room.game.member(user_id):
                return room_id
        return None

    def _require_free(self, user_id: int) -> None:
        if self._active_room_of(user_id) is not None:
            raise GameError("You are already in an unfinished game; leave it first")

    def _is_expired(self, room_id: str, room: _Room, now: float) -> bool:
        limit = FINISHED_ROOM_SECONDS if room.game.phase is Phase.FINISHED else IDLE_ROOM_SECONDS
        return now - room.last_activity >= limit and not self.is_connected(room_id)

    def _reap_locked(self) -> list[str]:
        now = self._clock()
        expired = [i for i, r in self._rooms.items() if self._is_expired(i, r, now)]
        for room_id in expired:
            del self._rooms[room_id]
        return expired

    def reap(self) -> list[str]:
        """Delete idle/finished rooms nobody is connected to; returns the removed room ids."""
        with self._lock:
            return self._reap_locked()

    def unsaved_results(self) -> list[tuple[str, Game]]:
        """Finished games whose result is not stored yet (one retry attempt is consumed per call)."""
        with self._lock:
            pending = []
            for room_id, room in self._rooms.items():
                finished = room.game.phase is Phase.FINISHED
                if finished and not room.persisted and room.persist_attempts < MAX_PERSIST_ATTEMPTS:
                    room.persist_attempts += 1
                    pending.append((room_id, room.game))
            return pending

    def mark_persisted(self, room_id: str) -> None:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is not None:
                room.persisted = True

    def create(self, user_id: int, username: str) -> tuple[str, Game]:
        with self._lock:
            self._require_free(user_id)
            self._reap_locked()
            if len(self._rooms) >= MAX_ROOMS:
                raise GameError("The server has too many rooms right now")
            room_id = secrets.token_urlsafe(ROOM_ID_BYTES)
            game = new_game(user_id, username)
            self._rooms[room_id] = _Room(game, self._clock())
            return room_id, game

    def join(self, room_id: str, user_id: int, username: str) -> Game:
        with self._lock:
            room = self._get(room_id)
            if room.game.member(user_id) is None:
                self._require_free(user_id)
            room.game = self._bump(add_player(room.game, user_id, username))
            room.last_activity = self._clock()
            return room.game

    def get(self, room_id: str) -> Game | None:
        with self._lock:
            room = self._rooms.get(room_id)
            return room.game if room else None

    def open_lobbies(self) -> list[tuple[str, Game]]:
        with self._lock:
            self._reap_locked()
            return [(i, r.game) for i, r in self._rooms.items() if r.game.phase is Phase.LOBBY]

    def update(self, room_id: str, transition: Callable[[Game], Game]) -> UpdateResult:
        """Apply a pure transition atomically; GameError leaves the room untouched."""
        with self._lock:
            room = self._get(room_id)
            game = self._bump(transition(room.game), room.game.version)
            room.game = game
            room.last_activity = self._clock()
            finished_now = (
                game.phase is Phase.FINISHED
                and not room.persisted
                and room.persist_attempts < MAX_PERSIST_ATTEMPTS
            )
            if finished_now:
                room.persist_attempts += 1
            deleted = not game.members()
            if deleted:
                del self._rooms[room_id]
            return UpdateResult(game, finished_now, deleted)

    @staticmethod
    def _bump(game: Game, previous: int | None = None) -> Game:
        base = game.version if previous is None else previous
        return replace(game, version=base + 1)

    def _get(self, room_id: str) -> _Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise RoomNotFound(room_id)
        return room
