from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.chat.social.service import REPORT_REASONS

ReportReason = Literal["spam", "abuse", "impersonation", "illegal", "other"]
assert set(REPORT_REASONS) == {"spam", "abuse", "impersonation", "illegal", "other"}


class PersonOut(BaseModel):
    user_id: int
    username: str
    display_name: str
    headline: str
    region: str
    avatar: str
    summary: str | None = None  # only when the viewer may read it
    relation: Literal["none", "friends", "requested", "incoming"] = "none"
    blocked: bool = False  # I blocked this person
    virtual: bool = False  # made by the platform, not a person: always shown as such
    age: int | None = None  # of a virtual person (a person's age is theirs to tell)
    interests: list[str] = []
    companion: bool = False  # I drew this virtual person


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["user", "message", "room", "object"]
    target_id: str = Field(min_length=1, max_length=64)
    reason: ReportReason
    details: str = Field(default="", max_length=500)


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_id: int
    target_type: str
    target_id: str
    reason: str
    details: str
    status: str
    created_at: datetime


class ReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["reviewed", "actioned"]

