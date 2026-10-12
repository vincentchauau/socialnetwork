from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

ROOM_PATTERN = r"^[A-Za-z0-9_-]{1,32}$"
MAX_MESSAGE_LENGTH = 2000


class IncomingMessage(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room: str
    username: str
    content: str
    created_at: datetime
