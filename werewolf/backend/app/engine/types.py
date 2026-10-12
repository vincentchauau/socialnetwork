"""Immutable game state. Nothing here performs I/O; every transition returns a new Game."""

from dataclasses import dataclass, replace
from enum import Enum

MIN_PLAYERS = 5
MAX_PLAYERS = 12
PLAYERS_PER_WOLF = 4  # 5-7 players: 1 wolf, 8-11: 2, 12: 3


class Role(str, Enum):
    VILLAGER = "villager"
    WEREWOLF = "werewolf"
    SEER = "seer"
    DOCTOR = "doctor"


class Phase(str, Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    VOTE = "vote"
    FINISHED = "finished"


class Winner(str, Enum):
    VILLAGE = "village"
    WOLVES = "wolves"


class GameError(ValueError):
    """An action that the rules do not allow right now."""


class ForbiddenAction(GameError):
    """The actor is not permitted to perform this action (e.g. host-only)."""


@dataclass(frozen=True)
class Player:
    user_id: int
    username: str
    role: Role | None = None
    alive: bool = True
    left: bool = False  # walked away from a running game; still listed for the result


@dataclass(frozen=True)
class Event:
    """A public log entry. `role` is only set when a death reveals it."""

    day: int
    kind: str  # night_death | peaceful_night | lynch | no_lynch | left | game_over
    player_id: int | None = None
    role: str | None = None


Pairs = tuple[tuple[int, int | None], ...]


@dataclass(frozen=True)
class Game:
    players: tuple[Player, ...]
    host_id: int
    phase: Phase = Phase.LOBBY
    day: int = 0
    wolf_votes: Pairs = ()
    seer_target: int | None = None
    doctor_target: int | None = None
    last_doctor_target: int | None = None
    seer_results: tuple[tuple[int, bool], ...] = ()  # (target id, is werewolf)
    votes: Pairs = ()
    events: tuple[Event, ...] = ()
    winner: Winner | None = None

    def find(self, user_id: int) -> Player | None:
        return next((p for p in self.players if p.user_id == user_id), None)

    def member(self, user_id: int) -> Player | None:
        player = self.find(user_id)
        return None if player is None or player.left else player

    def members(self) -> tuple[Player, ...]:
        return tuple(p for p in self.players if not p.left)

    def living(self, role: Role | None = None) -> tuple[Player, ...]:
        return tuple(
            p for p in self.players if p.alive and (role is None or p.role == role)
        )

    def with_player(self, updated: Player) -> "Game":
        players = tuple(updated if p.user_id == updated.user_id else p for p in self.players)
        return replace(self, players=players)

    def with_event(self, event: Event) -> "Game":
        return replace(self, events=self.events + (event,))


def set_pair(pairs: Pairs, key: int, value: int | None) -> Pairs:
    """A copy of `pairs` where `key` maps to `value` (replacing any previous entry)."""
    return tuple((k, v) for k, v in pairs if k != key) + ((key, value),)
