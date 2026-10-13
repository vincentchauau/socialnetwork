"""One room: seats (humans and bots), the lobby flow and the running game. In-memory, no I/O.

A human seat is (user_id, username) taken from the auth cookie; a bot seat has no user. The engine only knows
seat numbers (player id = seat index + 1), so everything user-related lives here.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from typing import Any, Callable

from app.engine import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    Ability,
    Faction,
    Game,
    GameError,
    Role,
    validate_roles,
)
from app.engine.chat import ChatMessage

BOT_NAMES = [
    "An", "Bình", "Cường", "Dũng", "Phúc", "Giang", "Hùng", "Khoa", "Linh", "Minh",
    "Nam", "Oanh", "Phong", "Quân", "Sơn", "Tùng", "Uyên", "Việt", "Xuân", "Yến",
    "Đạt", "Hà", "Lan", "Thảo", "Hương", "Trung", "Tâm", "Hải", "Long", "Mai",
    "Nhi", "Trang", "Vy", "Khánh", "Thắng", "Hiếu", "Ngọc", "Quỳnh", "Tú", "Bảo",
]
ROOM_PLACES = ["Làng", "Rừng", "Thung Lũng", "Đồi", "Thị Trấn", "Lâu Đài"]
ROOM_THEMES = [
    "Trăng Máu", "Sương Mù", "Đêm Đen", "Cú Mèo", "Trăng Tròn", "Bóng Tối",
    "Tiếng Hú", "Lửa Trại", "Cổ Thụ", "Đèn Lồng", "Gió Lạnh", "Hoàng Hôn",
]
CODE_LENGTH = 5
CODE_ALPHABET = string.ascii_uppercase


class RoomError(GameError):
    """The room is not in a state that allows this (HTTP 409)."""


class Forbidden(GameError):
    """The caller may not do this (HTTP 403)."""


class RoomNotFound(LookupError):
    """No such room (HTTP 404)."""


class CapacityError(GameError):
    """The server cannot take another room (HTTP 503)."""


def random_room_title(rng: random.Random | None = None) -> str:
    chooser = rng or random
    return f"{chooser.choice(ROOM_PLACES)} {chooser.choice(ROOM_THEMES)}"


def pick_names(count: int, taken: set[str] | None = None) -> list[str]:
    """Random bot names, unique and not in `taken` (case-insensitive); numbered when the list runs out."""
    used = {n.casefold() for n in (taken or set())}
    available = [n for n in BOT_NAMES if n.casefold() not in used]
    random.shuffle(available)
    names: list[str] = []
    for i in range(count):
        if i < len(available):
            names.append(available[i])
            continue
        n = i
        while True:
            candidate = f"{random.choice(BOT_NAMES)} {n}"
            if candidate.casefold() not in used and candidate not in names:
                break
            n += 1
        names.append(candidate)
    return names


@dataclass
class Seat:
    name: str
    user_id: int | None = None  # None = bot
    faction: Faction | None = None  # setup role; None = dealt at random when the game starts
    ability: Ability | None = None
    started_by: int | None = None  # the human who held the seat when the game started (result history)

    @property
    def is_bot(self) -> bool:
        return self.user_id is None


@dataclass(frozen=True)
class PlayerRecord:
    user_id: int
    username: str
    faction: str
    ability: str
    outcome: str  # won | draw | lost
    survived: bool
    days_survived: int


@dataclass
class GameRecord:
    """The result of one finished game, waiting to be stored (bots are never included)."""

    room_code: str
    winner: str  # faction code or DRAW
    days: int
    size: int
    players: tuple[PlayerRecord, ...]
    attempts: int = 0
    saved: bool = False
    inflight: bool = False  # a write is in progress (never store the same record twice)


@dataclass
class Room:
    code: str
    host_id: int
    title: str
    seats: list[Seat]
    clock: Callable[[], float]
    listed: bool = True
    timer: int = 0  # seconds per night turn (day = double); 0 = no limit
    events: bool = True
    dead_talk: bool = True
    game: Game | None = None
    history: dict[str, int] = field(default_factory=lambda: {"games": 0, "VILLAGER": 0, "WOLF": 0, "GHOST": 0, "draw": 0})
    records: list[GameRecord] = field(default_factory=list)
    last_active: float = 0.0
    _recorded: Game | None = None

    def __post_init__(self) -> None:
        self.last_active = self.clock()

    # ---- queries ----
    def touch(self) -> None:
        self.last_active = self.clock()

    def seat_index(self, user_id: int | None) -> int | None:
        if user_id is None:
            return None
        return next((i for i, s in enumerate(self.seats) if s.user_id == user_id), None)

    def seat_of(self, user_id: int | None) -> Seat | None:
        index = self.seat_index(user_id)
        return None if index is None else self.seats[index]

    def player_id(self, user_id: int) -> int | None:
        index = self.seat_index(user_id)
        return None if index is None else index + 1

    def humans(self) -> list[Seat]:
        return [s for s in self.seats if s.user_id is not None]

    @property
    def started(self) -> bool:
        return self.game is not None

    @property
    def finished(self) -> bool:
        return self.game is not None and self.game.game_over

    @property
    def open_seats(self) -> int:
        return sum(s.is_bot for s in self.seats) if self.game is None else 0

    def _require_host(self, user_id: int) -> None:
        if user_id != self.host_id:
            raise Forbidden("Chỉ chủ phòng mới được thực hiện")

    def _require_game(self) -> Game:
        if self.game is None:
            raise RoomError("Game chưa bắt đầu")
        return self.game

    def _require_pid(self, user_id: int) -> int:
        pid = self.player_id(user_id)
        if pid is None:
            raise Forbidden("Bạn không ở trong phòng này")
        return pid

    def _taken_names(self) -> set[str]:
        return {s.name for s in self.seats}

    # ---- lobby ----
    def join(self, user_id: int, username: str, rng: random.Random | None = None) -> None:
        """A human takes over one bot seat (the one with their name if any, else a random one) and its role."""
        if self.game is not None:
            raise RoomError("Phòng đã bắt đầu chơi")
        if self.seat_index(user_id) is not None:
            raise RoomError("Bạn đã ở trong phòng này")
        bots = [i for i, s in enumerate(self.seats) if s.is_bot]
        if not bots:
            raise RoomError(f"Phòng đầy (tối đa {len(self.seats)} người)")
        same = [i for i in bots if self.seats[i].name.casefold() == username.casefold()]
        if not same and any(s.name.casefold() == username.casefold() for s in self.seats):
            raise RoomError("Tên đã có người dùng trong phòng")
        index = same[0] if same else (rng or random).choice(bots)
        seat = self.seats[index]
        seat.user_id, seat.name = user_id, username
        self.touch()

    def add_bots(self, user_id: int, count: int) -> None:
        self._require_host(user_id)
        if self.game is not None:
            raise RoomError("Phòng đã bắt đầu chơi")
        if len(self.seats) + count > MAX_PLAYERS:
            raise RoomError(f"Phòng đầy (tối đa {MAX_PLAYERS} người)")
        for name in pick_names(count, self._taken_names()):
            self.seats.append(Seat(name))
        self.touch()

    def fill_to_minimum(self) -> None:
        missing = MIN_PLAYERS - len(self.seats)
        if missing > 0:
            for name in pick_names(missing, self._taken_names()):
                self.seats.append(Seat(name))

    def start(self, user_id: int) -> None:
        self._require_host(user_id)
        if self.game is not None:
            raise RoomError("Game đã bắt đầu")
        self._begin()

    def _begin(self) -> None:
        if len(self.seats) < MIN_PLAYERS:
            raise RoomError(f"Cần ít nhất {MIN_PLAYERS} người (hiện có {len(self.seats)})")
        if not self.humans():
            raise RoomError("Cần ít nhất 1 người chơi thật")
        preset = all(s.faction and s.ability for s in self.seats)
        roles: list[Role] | None = [(s.faction, s.ability) for s in self.seats] if preset else None  # type: ignore[misc]
        if roles:
            validate_roles(roles)
        game = Game([(s.name, s.is_bot) for s in self.seats], roles=roles, events=self.events,
                    timer=self.timer or None, dead_talk=self.dead_talk, clock=self.clock)
        game.start()
        self.game = game
        for seat in self.seats:
            seat.started_by = seat.user_id
        self.touch()

    # ---- result / rematch / reset ----
    def collect_result(self) -> GameRecord | None:
        """The record of the game that just ended (exactly once per game), or None."""
        game = self.game
        if game is None or not game.game_over or self._recorded is game:
            return None
        self._recorded = game
        winner = game.winner.name if game.winner else "DRAW"
        self.history["games"] += 1
        self.history[game.winner.name if game.winner else "draw"] += 1
        players = []
        for seat, p in zip(self.seats, game.players):
            if seat.started_by is None:
                continue
            outcome = "draw" if game.winner is None else ("won" if p.faction == game.winner else "lost")
            players.append(PlayerRecord(
                seat.started_by, seat.name, p.faction.name, p.ability.name, outcome, p.alive,
                game.night if p.died_on is None else p.died_on))
        record = GameRecord(self.code, winner, game.night, len(game.players), tuple(players))
        self.records.append(record)
        return record

    def rematch(self, user_id: int) -> None:
        self._require_host(user_id)
        if self.game is None or not self.game.game_over:
            raise RoomError("Chỉ chơi lại được khi ván đã kết thúc")
        self.collect_result()
        for seat in self.seats:
            seat.faction = seat.ability = None
        self.game = None
        self._begin()

    def reset(self, user_id: int) -> None:
        self._require_host(user_id)
        self.collect_result()
        self.game = None
        self.seats = [s for s in self.seats if not s.is_bot]
        for seat in self.seats:
            seat.faction = seat.ability = seat.started_by = None
        self.fill_to_minimum()
        self.touch()

    def force(self, user_id: int) -> None:
        self._require_host(user_id)
        self._require_game().force()
        self.touch()

    def tick(self) -> bool:
        return self.game is not None and self.game.tick()

    # ---- leaving ----
    def leave(self, user_id: int) -> bool:
        """The user leaves; their seat goes to a bot. Returns True when no human is left (room is dead)."""
        index = self.seat_index(user_id)
        if index is None:
            raise RoomError("Bạn không ở trong phòng này")
        seat = self.seats[index]
        if self.game is None:
            seat.user_id, seat.name = None, pick_names(1, self._taken_names())[0]
        else:
            seat.user_id = None  # keeps its name; the engine now plays it as a bot
            if not self.game.game_over:
                self.game.take_over(index + 1)
        humans = self.humans()
        if user_id == self.host_id and humans:
            self.host_id = humans[0].user_id  # type: ignore[assignment]
        self.touch()
        return not humans

    # ---- in game ----
    def submit(self, user_id: int, target: int, kind: str = "ability") -> None:
        game = self._require_game()
        game.submit(self._require_pid(user_id), target, kind)
        self.touch()

    def chat(self, user_id: int, text: str, target: int = 0) -> ChatMessage:
        game = self._require_game()
        message = game.post_chat(self._require_pid(user_id), text, target)
        self.touch()
        return message

    def chat_recipients(self, message: ChatMessage) -> list[int]:
        """User ids that may read `message` (same visibility rule as the state snapshot)."""
        game = self._require_game()
        return [seat.user_id for i, seat in enumerate(self.seats)
                if seat.user_id is not None and game.message_visible(game.players[i], message, game.game_over)]

    def chat_payload(self, message: ChatMessage) -> dict[str, Any]:
        return self._require_game().chat_entry(message)

    def perspective(self, user_id: int, seat_no: int) -> dict[str, Any]:
        """What seat `seat_no` knows. Only for dead players, or for everyone once the game is over."""
        game = self._require_game()
        if not game.can_see_everything(self._require_pid(user_id)):
            raise Forbidden("Chỉ người đã chết hoặc khi ván kết thúc mới xem được góc nhìn người khác")
        if not 1 <= seat_no <= len(game.players):
            raise RoomNotFound("Người chơi không tồn tại")
        return game.view_for(seat_no, perspective=True)

    # ---- views ----
    def summary(self) -> dict[str, Any]:
        host = self.seat_of(self.host_id)
        return {"id": self.code, "title": self.title, "host": host.name if host else "",
                "players": len(self.humans()), "seats": len(self.seats), "open_seats": self.open_seats,
                "max_players": MAX_PLAYERS, "timer": self.timer, "events": self.events}

    def state_for(self, user_id: int | None) -> dict[str, Any]:
        """The room as `user_id` may see it. A role (faction/ability) is only ever shown for the caller's own seat."""
        index = self.seat_index(user_id)
        game = self.game
        members = []
        for i, seat in enumerate(self.seats):
            member: dict[str, Any] = {"seat": i + 1, "name": seat.name, "isBot": seat.is_bot,
                                      "isHost": seat.user_id is not None and seat.user_id == self.host_id,
                                      "isYou": i == index, "faction": None, "ability": None}
            if i == index and game is None and seat.faction and seat.ability:
                member["faction"] = {"code": seat.faction.name, "label": seat.faction.value}
                member["ability"] = {"code": seat.ability.name, "label": seat.ability.value}
            members.append(member)
        return {
            "code": self.code,
            "title": self.title,
            "isHost": user_id is not None and user_id == self.host_id,
            "you": None if index is None else {"username": self.seats[index].name, "seat": index + 1},
            "minPlayers": MIN_PLAYERS,
            "maxPlayers": MAX_PLAYERS,
            "members": members,
            "timer": self.timer,
            "events": self.events,
            "deadTalk": self.dead_talk,
            "listed": self.listed,
            "history": dict(self.history),
            "started": game is not None,
            "game": game.view_for(index + 1) if game is not None and index is not None else None,
        }
