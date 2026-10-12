from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

TITLE_MAX = 120
COMPANY_MAX = 120
LOCATION_MAX = 120
DESCRIPTION_MAX = 10_000
MAX_TAGS = 10
TAG_MAX = 30
SALARY_MAX_VALUE = 10_000_000_000
COVER_LETTER_MAX = 5_000
RESUME_MAX = 20_000
EMAIL_MAX = 254
NOTE_MAX = 2_000
HEADLINE_MAX = 120
MAX_SKILLS = 20
SKILL_MAX = 40
ABOUT_MAX = 2_000
SNIPPET_MAX = 200

TAG_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9+#._-]*$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"
EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$"

EmploymentType = Literal["full_time", "part_time", "contract", "internship"]
PostingStatus = Literal["open", "closed"]
ApplicationStatus = Literal["submitted", "reviewing", "shortlisted", "rejected", "hired"]
NON_NULLABLE_UPDATE_FIELDS = (
    "title", "company", "location", "remote", "employment_type", "currency",
    "description", "tags", "status",
)


def as_utc(value: datetime) -> datetime:
    """Naive datetimes (SQLite, or clients that omit an offset) are taken as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_future(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    normalised = as_utc(value)
    if normalised <= datetime.now(timezone.utc):
        raise ValueError("expires_at must be in the future")
    return normalised


UtcDatetime = Annotated[datetime, AfterValidator(as_utc)]
FutureDatetime = Annotated[datetime | None, AfterValidator(_require_future)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True,
                                       min_length=1, max_length=TAG_MAX, pattern=TAG_PATTERN)]
Skill = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SKILL_MAX)]
Salary = Annotated[int, Field(ge=0, le=SALARY_MAX_VALUE)]
Email = Annotated[str, StringConstraints(max_length=EMAIL_MAX, pattern=EMAIL_PATTERN)]


def unique_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tags))


class PostingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    company: str = Field(min_length=1, max_length=COMPANY_MAX)
    location: str = Field(default="", max_length=LOCATION_MAX)
    remote: bool = False
    employment_type: EmploymentType
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: str = Field(default="USD", pattern=CURRENCY_PATTERN)
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_TAGS)
    expires_at: FutureDatetime = None

    _dedupe_tags = field_validator("tags")(unique_tags)

    @model_validator(mode="after")
    def _salary_range(self) -> "PostingCreate":
        check_salary_range(self.salary_min, self.salary_max)
        return self


def check_salary_range(minimum: int | None, maximum: int | None) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("salary_min must not exceed salary_max")


class PostingUpdate(BaseModel):
    """Partial update; salary and expiry may be set to null to clear them."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    company: str | None = Field(default=None, min_length=1, max_length=COMPANY_MAX)
    location: str | None = Field(default=None, max_length=LOCATION_MAX)
    remote: bool | None = None
    employment_type: EmploymentType | None = None
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_TAGS)
    status: PostingStatus | None = None
    expires_at: FutureDatetime = None

    @field_validator("tags")
    @classmethod
    def _dedupe_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else unique_tags(tags)

    @model_validator(mode="after")
    def _no_null_for_required(self) -> "PostingUpdate":
        for name in NON_NULLABLE_UPDATE_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class PostingSummary(BaseModel):
    id: int
    title: str
    company: str
    location: str
    remote: bool
    employment_type: EmploymentType
    salary_min: int | None
    salary_max: int | None
    currency: str
    snippet: str
    tags: list[str]
    status: PostingStatus
    expired: bool
    expires_at: UtcDatetime | None
    created_at: UtcDatetime
    owner_username: str
    is_owner: bool
    applied: bool
    saved: bool
    application_count: int | None = None


class PostingDetail(PostingSummary):
    description: str


class PostingPage(BaseModel):
    items: list[PostingSummary]
    next_cursor: str | None


class ApplicationCreate(BaseModel):
    cover_letter: str = Field(default="", max_length=COVER_LETTER_MAX)
    resume_text: str = Field(default="", max_length=RESUME_MAX)
    contact_email: Email | None = None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class ProfileIn(BaseModel):
    headline: str = Field(default="", max_length=HEADLINE_MAX)
    skills: list[Skill] = Field(default_factory=list, max_length=MAX_SKILLS)
    about: str = Field(default="", max_length=ABOUT_MAX)
    open_to_work: bool = False


class ProfileOut(ProfileIn):
    username: str


class ApplicationOut(BaseModel):
    """What the applicant sees: never the employer's private note."""

    id: int
    job_id: int
    job_title: str
    company: str
    status: ApplicationStatus
    cover_letter: str
    resume_text: str
    contact_email: str | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ApplicantOut(BaseModel):
    """What the employer sees about one application."""

    id: int
    job_id: int
    applicant_username: str
    status: ApplicationStatus
    cover_letter: str
    resume_text: str
    contact_email: str | None
    note: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    profile: ProfileOut | None
