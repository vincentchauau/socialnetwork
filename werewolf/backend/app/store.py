"""In-memory room registry (single process, like chat's RoomHub). Thread-safe."""

import random
import secrets
import threading
from dataclasses import dataclass
from typing import Callable

from app.engine import Game, GameError, Phase, add_player, new_game

MAX_ROOMS = 200
ROOM_ID_BYTES = 6  # token_urlsafe(6) -> 8 chars from [A-Za-z0-9_-]


class RoomNotFound(LookupError):
    pass


@dataclass
class _Room:
    game: Game
    persisted: bool = False


@dataclass(frozen=True)
class UpdateResult:
    game: Game
    finished_now: bool  # True exactly once: the first time the game is seen finished
    deleted: bool


class RoomStore:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rooms: dict[str, _Room] = {}
        self._lock = threading.Lock()
        self.rng = rng or random.Random(secrets.randbits(64))

    def _active_room_of(self, user_id: int) -> str | None:
        for room_id, room in self._rooms.items():
            if room.game.phase is not Phase.FINISHED and room.game.member(user_id):
                return room_id
        return None

    def _require_free(self, user_id: int) -> None:
        if self._active_room_of(user_id) is not None:
            raise GameError("You are already in an unfinished game; leave it first")

    def create(self, user_id: int, username: str) -> tuple[str, Game]:
        with self._lock:
            self._require_free(user_id)
            if len(self._rooms) >= MAX_ROOMS:
                raise GameError("The server has too many rooms right now")
            room_id = secrets.token_urlsafe(ROOM_ID_BYTES)
            game = new_game(user_id, username)
            self._rooms[room_id] = _Room(game)
            return room_id, game

    def join(self, room_id: str, user_id: int, username: str) -> Game:
        with self._lock:
            room = self._get(room_id)
            if room.game.member(user_id) is None:
                self._require_free(user_id)
            room.game = add_player(room.game, user_id, username)
            return room.game

    def get(self, room_id: str) -> Game | None:
        with self._lock:
            room = self._rooms.get(room_id)
            return room.game if room else None

    def open_lobbies(self) -> list[tuple[str, Game]]:
        with self._lock:
            return [(i, r.game) for i, r in self._rooms.items() if r.game.phase is Phase.LOBBY]

    def update(self, room_id: str, transition: Callable[[Game], Game]) -> UpdateResult:
        """Apply a pure transition atomically; GameError leaves the room untouched."""
        with self._lock:
            room = self._get(room_id)
            game = transition(room.game)
            room.game = game
            finished_now = game.phase is Phase.FINISHED and not room.persisted
            if finished_now:
                room.persisted = True
            deleted = not game.members()
            if deleted:
                del self._rooms[room_id]
            return UpdateResult(game, finished_now, deleted)

    def _get(self, room_id: str) -> _Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise RoomNotFound(room_id)
        return room
