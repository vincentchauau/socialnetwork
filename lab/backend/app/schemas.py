from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
LogMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class NotificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    body: Body


class LogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["info", "warn", "error"]
    message: LogMessage


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    title: str
    body: str
    status: str
    attempts: int
    created_at: datetime = Field(serialization_alias="createdAt")
    processed_at: datetime | None = Field(serialization_alias="processedAt")


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    level: str = Field(validation_alias="title")
    message: str = Field(validation_alias="body")
    created_at: datetime = Field(serialization_alias="createdAt")
    partition: int = Field(validation_alias="kafka_partition")
    offset: int = Field(validation_alias="kafka_offset")
