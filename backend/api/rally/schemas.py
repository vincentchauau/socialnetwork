from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict



class MatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    video_name: str
    created_at: datetime


class PeopleOut(BaseModel):
    status: str  # idle, running, done or failed
    samples: list[dict[str, Any]]  # one per sample of the video: t_ms and the people on the court
