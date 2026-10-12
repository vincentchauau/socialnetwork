from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

ROOM_PATTERN = r"^[A-Za-z0-9_-]{1,32}$"
MAX_CHAT_LENGTH = 500
HISTORY_DEFAULT_LIMIT = 20
HISTORY_MAX_LIMIT = 100


class ActionMsg(BaseModel):
    type: Literal["action"]
    target: int = Field(ge=1)


class VoteMsg(BaseModel):
    type: Literal["vote"]
    target: int | None = Field(default=None, ge=1)  # null = abstain


class ChatMsg(BaseModel):
    type: Literal["chat"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CHAT_LENGTH)]


class AdvanceMsg(BaseModel):
    type: Literal["advance"]


ClientMessage = Annotated[ActionMsg | VoteMsg | ChatMsg | AdvanceMsg, Field(discriminator="type")]
client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


class RoomSummary(BaseModel):
    id: str
    host: str
    players: int
    max_players: int


class HistoryPlayer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    role: str
    survived: bool


class HistoryEntry(BaseModel):
    room_id: str
    finished_at: datetime
    winner: str
    days: int
    your_role: str
    won: bool
    players: list[HistoryPlayer]
