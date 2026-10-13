from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.engine import MAX_PLAYERS, MAX_TIMER, MIN_PLAYERS, MIN_TIMER

ROOM_PATTERN = r"^[A-Za-z]{5}$"
HISTORY_DEFAULT_LIMIT = 20
HISTORY_MAX_LIMIT = 100
MAX_CHAT_INPUT = 400  # the engine then enforces its own 140 characters on the cleaned text


class SeatSpec(BaseModel):
    faction: str
    ability: str


class CreateBody(BaseModel):
    """`seats` (one per seat, seat 1 = host) or `count` (random roles at start); both absent = 5 seats."""

    count: int | None = Field(default=None, ge=MIN_PLAYERS, le=MAX_PLAYERS)
    seats: list[SeatSpec] | None = Field(default=None, max_length=MAX_PLAYERS)
    roomName: Annotated[str, Field(max_length=30)] | None = None
    roomCode: Annotated[str, Field(pattern=ROOM_PATTERN)] | None = None
    start: bool = False
    timerSeconds: int = 0  # 0 = off, else MIN_TIMER..MAX_TIMER (the UI offers 0/30/60/90)
    events: bool = True
    deadTalk: bool = True
    listed: bool = True

    @field_validator("timerSeconds")
    @classmethod
    def _timer(cls, value: int) -> int:
        if value != 0 and not MIN_TIMER <= value <= MAX_TIMER:
            raise ValueError(f"must be 0 or {MIN_TIMER}..{MAX_TIMER}")
        return value


class BotsBody(BaseModel):
    count: int = Field(ge=1, le=MAX_PLAYERS - 1)


class ActionBody(BaseModel):
    target: int = Field(ge=0)
    kind: Literal["ability", "wolf"] = "ability"  # "wolf": the wolves' night kill vote (target 0 = abstain)


class ChatBody(BaseModel):
    text: Annotated[str, Field(max_length=MAX_CHAT_INPUT)]
    target: int = Field(default=0, ge=0)


class ActionMsg(ActionBody):
    type: Literal["action"]


class ChatMsg(ChatBody):
    type: Literal["chat"]


class ForceMsg(BaseModel):
    type: Literal["force"]


class RoomSummary(BaseModel):
    id: str
    title: str
    host: str
    players: int
    seats: int
    open_seats: int
    max_players: int
    timer: int
    events: bool


class HistoryPlayer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    faction: str
    ability: str
    outcome: str
    survived: bool


class HistoryEntry(BaseModel):
    game_id: int
    room_id: str
    finished_at: datetime
    winner: str  # VILLAGER | WOLF | GHOST | DRAW
    days: int
    size: int
    your_faction: str
    your_ability: str
    your_outcome: str  # won | draw | lost
    won: bool
    survived: bool
    days_survived: int
    players: list[HistoryPlayer]

