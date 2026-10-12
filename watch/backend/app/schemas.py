from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

TITLE_MAX = 120
DESCRIPTION_MAX = 2000
TAGS_MAX = 10
TAG_MAX_LEN = 30
QUERY_MAX = 100
PAGE_DEFAULT_LIMIT = 20
PAGE_MAX_LIMIT = 50
MAX_PROGRESS_SECONDS = 7 * 24 * 3600


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    tags: list[str]
    owner: str
    owner_id: int
    content_type: str
    size_bytes: int
    views: int
    created_at: datetime


class VideoDetail(VideoOut):
    in_watchlist: bool
    progress_seconds: float


class VideoPage(BaseModel):
    items: list[VideoOut]
    next_cursor: int | None


class ProgressIn(BaseModel):
    seconds: float = Field(ge=0, le=MAX_PROGRESS_SECONDS, allow_inf_nan=False)


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seconds: float
    updated_at: datetime


class HistoryItem(BaseModel):
    video: VideoOut
    seconds: float
    updated_at: datetime
