from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_HITS = 500
MAX_RALLY_MS = 60 * 60 * 1000  # a rally is at most one hour long
MAX_VIDEO_MS = 24 * 60 * 60 * 1000


class RallyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(ge=0, le=MAX_VIDEO_MS)
    end_ms: int = Field(ge=0, le=MAX_VIDEO_MS)
    hits: int = Field(ge=0, le=MAX_HITS)
    winner: Literal["A", "B"]

    @model_validator(mode="after")
    def check_span(self) -> "RallyIn":
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be after start_ms")
        if self.end_ms - self.start_ms > MAX_RALLY_MS:
            raise ValueError("A rally cannot be longer than one hour")
        return self


class RallyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    start_ms: int
    end_ms: int
    hits: int
    winner: str


class MatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    video_name: str
    created_at: datetime


class StatsOut(BaseModel):
    rallies: int
    score: dict[str, int]
    avg_hits: float
    max_hits: int
    avg_duration_ms: float
    longest_rally_ms: int


class PeopleOut(BaseModel):
    status: str  # idle, running, done or failed
    samples: list[dict[str, Any]]  # one per sample of the video: t_ms and the people on the court


class MatchOut(MatchSummary):
    rallies: list[RallyOut]
    stats: StatsOut
