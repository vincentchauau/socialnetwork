from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

CAPTION_MAX = 500
COMMENT_MAX = 500

CommentText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=COMMENT_MAX)]


class CommentIn(BaseModel):
    content: CommentText


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    username: str
    content: str
    created_at: datetime


class PhotoOut(BaseModel):
    id: int
    username: str
    caption: str | None
    width: int
    height: int
    created_at: datetime
    like_count: int
    comment_count: int
    liked_by_me: bool
    is_mine: bool
    image_url: str
    thumb_url: str


class PhotoPage(BaseModel):
    items: list[PhotoOut]
    next_cursor: int | None = Field(description="Pass as ?cursor= to get the next page")


class LikeState(BaseModel):
    liked: bool
    like_count: int
