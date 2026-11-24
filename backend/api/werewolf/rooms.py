"""One room: seats (humans and bots), the lobby flow and the running game. In-memory, no I/O.

A human seat is (user_id, username) taken from the auth cookie; a bot seat has no user. The engine only knows
seat numbers (player id = seat index + 1), so everything user-related lives here.
"""

from __future__ import annotations

import random
import string
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from api.werewolf.engine import (
    MAX_PLAYERS,
    MAX_TIMER,
    MIN_PLAYERS,
    MIN_TIMER,
    Ability,
    Faction,
    Game,
    GameError,
    Role,
    suggest_roles,
    validate_roles,
)
from api.werewolf.engine.chat import ChatMessage

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


class GameStarted(RoomError):
    """The game has begun: nobody takes a seat any more."""


class RoomFull(RoomError):
    """Every seat is taken by a person."""


class TooManyRooms(RoomError):
    """The person already holds a seat in as many rooms as the server allows."""


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
    origin: str = ""  # who the seat is for when the machine plays it: "virtual" (a virtual person of the chat room), "human" (a person of the room who has not sat yet), "" (a filler)

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
    roles: tuple[str, ...] = ()  # every role, as a finished game shows them to the players
    seen: tuple[str, ...] = ()  # what happened that all the players saw (never what only some of them saw)
    attempts: int = 0
    saved: bool = False
    inflight: bool = False  # a write is in progress (never store the same record twice)
    announced: bool = False  # the chat was told (once) that this game is over


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
            raise GameStarted("Phòng đã bắt đầu chơi")
        if self.seat_index(user_id) is not None:
            raise RoomError("Bạn đã ở trong phòng này")
        bots = [i for i, s in enumerate(self.seats) if s.is_bot]
        if not bots:
            raise RoomFull(f"Phòng đầy (tối đa {len(self.seats)} người)")
        same = [i for i in bots if self.seats[i].name.casefold() == username.casefold()]
        if not same and any(s.name.casefold() == username.casefold() for s in self.seats):
            raise RoomError("Tên đã có người dùng trong phòng")
        index = same[0] if same else (rng or random).choice(bots)
        seat = self.seats[index]
        seat.user_id, seat.name = user_id, username
        self.touch()

    def add_bots(self, user_id: int, count: int) -> None:
        """The host adds machine seats before the game starts (up to the limit of the room); the new seats have no role yet."""
        self._require_host(user_id)
        if self.game is not None:
            raise RoomError("Phòng đã bắt đầu chơi")
        if len(self.seats) + count > MAX_PLAYERS:
            raise RoomFull(f"Phòng đầy (tối đa {MAX_PLAYERS} người)")
        for _ in range(count):
            self.seats.append(Seat(pick_names(1, self._taken_names())[0]))
        self.touch()

    def set_options(self, user_id: int, timer: int | None = None, events: bool | None = None, dead_talk: bool | None = None) -> None:
        """The host changes how the game is played before it starts: the seconds of a night turn (0 = no limit), the event cards, whether the dead chat with the living."""
        self._require_host(user_id)
        if self.game is not None:
            raise RoomError("Phòng đã bắt đầu chơi")
        if timer is not None:
            if timer and not MIN_TIMER <= timer <= MAX_TIMER:
                raise RoomError(f"Đồng hồ phải từ {MIN_TIMER} đến {MAX_TIMER} giây")
            self.timer = timer
        if events is not None:
            self.events = events
        if dead_talk is not None:
            self.dead_talk = dead_talk
        self.touch()

    def set_roles(self, user_id: int, roles: list[Role] | None, randomise: bool = False, banned: tuple[Ability, ...] = ()) -> None:
        """The host sets the role of every seat before the game starts: `randomise` deals a fresh balanced set to all the seats, `roles`
        is one (faction, ability) per seat (checked against the rules), and neither clears the setup (the roles are dealt when the game starts)."""
        self._require_host(user_id)
        if self.game is not None:
            raise RoomError("Phòng đã bắt đầu chơi")
        self.fill_to_minimum()
        if randomise:
            roles = suggest_roles(len(self.seats), banned)
            self.banned = tuple(banned)  # a later change of the number of seats deals again without them
        if roles is None:
            for seat in self.seats:
                seat.faction = seat.ability = None
        else:
            if len(roles) != len(self.seats):
                raise RoomError(f"Cần đúng {len(self.seats)} vai, một vai cho mỗi ghế")
            validate_roles(roles)
            for seat, (faction, ability) in zip(self.seats, roles):
                seat.faction, seat.ability = faction, ability
        self.touch()

    def follow_chat(self, names: list[tuple[str, str]], seats: int) -> bool:
        """Before the game starts, the seats are the people of the chat room: one for each (5 at least), named after them (`names` are
        (name, kind) pairs, kind `virtual` or `human`). The seats of the people who have not sat in the game yet are played by the machine
        until they do (`join` gives a person the seat of their name); the seats nobody is named for are fillers with random names, and are
        taken away when there are more than the room needs. Returns whether anything changed."""
        if self.game is not None:
            return False
        before = [(seat.name, seat.user_id, getattr(seat, "origin", "")) for seat in self.seats]
        was_dealt = any(seat.faction for seat in self.seats)
        count_before = len(self.seats)
        wanted = min(max(seats, MIN_PLAYERS), MAX_PLAYERS)
        named = {name.casefold() for name, _ in names}
        extra = len(self.seats) - wanted
        for seat in [s for s in reversed(self.seats) if s.is_bot and s.name.casefold() not in named]:
            if extra <= 0:
                break
            self.seats.remove(seat)
            extra -= 1
        while len(self.seats) < wanted:
            self.seats.append(Seat(pick_names(1, self._taken_names())[0]))
        kinds = {name.casefold(): kind for name, kind in names}
        seated = {seat.name.casefold() for seat in self.seats}
        missing = [(name, kind) for name, kind in names if name.casefold() not in seated]
        for seat in self.seats:
            if seat.is_bot and seat.name.casefold() not in named and missing:
                seat.name, seat.origin = missing.pop(0)
        for seat in self.seats:  # who each machine seat is for (a seat that was named earlier keeps its name and gets its kind)
            seat.origin = kinds.get(seat.name.casefold(), "") if seat.is_bot else ""
        if was_dealt and len(self.seats) != count_before:  # the roles the host dealt were for another number of people: deal again for this one
            for seat, (faction, ability) in zip(self.seats, suggest_roles(len(self.seats), getattr(self, "banned", ()))):
                seat.faction, seat.ability = faction, ability
        changed = before != [(seat.name, seat.user_id, getattr(seat, "origin", "")) for seat in self.seats]
        if changed:
            self.touch()
        return changed

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
        record = GameRecord(self.code, winner, game.night, len(game.players), tuple(players), *self._public_lines(game))
        self.records.append(record)
        return record

    def _public_lines(self, game) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """The roles of everybody (a finished game shows them) and the lines of the log that were for everybody. A line that was for a
        few (what a wolf or a seer learned alone) is not here: the log keeps its audience."""
        roles = tuple(f"{seat.name}: {p.faction.value} · {p.ability.value}" for seat, p in zip(self.seats, game.players))
        seen = tuple(event.text for event in game.events if event.audience is None)
        return roles, seen

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
            member: dict[str, Any] = {"seat": i + 1, "name": seat.name, "isBot": seat.is_bot, "origin": getattr(seat, "origin", "") if seat.is_bot else "",
                                      "isHost": seat.user_id is not None and seat.user_id == self.host_id,
                                      "isYou": i == index, "faction": None, "ability": None}
            if i == index and game is None and seat.faction and seat.ability:
                member["faction"] = {"code": seat.faction.name, "label": seat.faction.value}
                member["ability"] = {"code": seat.ability.name, "label": seat.ability.value}
            members.append(member)
        host_sees = user_id is not None and user_id == self.host_id and game is None
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
            # what only the host sees before the game: the role set for each seat (None where it is left to be dealt at the start)
            **({"setup": [None if not (s.faction and s.ability) else {"faction": {"code": s.faction.name, "label": s.faction.value}, "ability": {"code": s.ability.name, "label": s.ability.value}} for s in self.seats]} if host_sees else {}),
            "game": game.view_for(index + 1) if game is not None and index is not None else None,
        }
