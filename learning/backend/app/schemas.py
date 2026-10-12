import re
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

Level = Literal["beginner", "intermediate", "advanced"]

TITLE_MAX = 120
SUMMARY_MAX = 1000
TAG_MAX = 30
MAX_TAGS = 10
CONTENT_MAX = 20000
VIDEO_URL_MAX = 500
MAX_LESSONS_PER_COURSE = 100
TAG_PATTERN = r"^[a-z0-9][a-z0-9 \-]*$"

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]


def _check_tag(tag: str) -> str:
    cleaned = tag.strip().lower()
    if not cleaned or len(cleaned) > TAG_MAX or not re.fullmatch(TAG_PATTERN, cleaned):
        raise ValueError("Tags use letters, digits, spaces and hyphens (max 30)")
    return cleaned


def _check_https_url(value: str) -> str:
    parts = urlsplit(value)
    has_blank = any(ch.isspace() or ord(ch) < 32 for ch in value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or has_blank
    ):
        raise ValueError("Video URL must be a valid https:// link")
    return value


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; every stored time is UTC, so restore it."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
Tag = Annotated[str, AfterValidator(_check_tag)]
VideoUrl = Annotated[str, Field(max_length=VIDEO_URL_MAX), AfterValidator(_check_https_url)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CourseIn(StrictModel):
    title: Title
    summary: Annotated[str, Field(max_length=SUMMARY_MAX)] = ""
    level: Level = "beginner"
    tags: Annotated[list[Tag], Field(max_length=MAX_TAGS)] = []
    published: bool = False


class CoursePatch(StrictModel):
    title: Title | None = None
    summary: Annotated[str, Field(max_length=SUMMARY_MAX)] | None = None
    level: Level | None = None
    tags: Annotated[list[Tag], Field(max_length=MAX_TAGS)] | None = None
    published: bool | None = None


class LessonIn(StrictModel):
    title: Title
    content: Annotated[str, Field(max_length=CONTENT_MAX)] = ""
    video_url: VideoUrl | None = None


class LessonPatch(StrictModel):
    title: Title | None = None
    content: Annotated[str, Field(max_length=CONTENT_MAX)] | None = None
    video_url: VideoUrl | None = None


class LessonOrderIn(StrictModel):
    lesson_ids: Annotated[list[int], Field(max_length=MAX_LESSONS_PER_COURSE)]


class QuizBrief(BaseModel):
    id: int
    title: str
    pass_percent: int
    question_count: int
    best_score: int | None
    passed: bool


class LessonOutline(BaseModel):
    id: int
    title: str
    position: int
    has_quiz: bool
    completed: bool


class LessonOut(BaseModel):
    id: int
    course_id: int
    title: str
    content: str
    video_url: str | None
    position: int
    completed: bool
    quiz: QuizBrief | None


class CourseSummary(BaseModel):
    id: int
    title: str
    summary: str
    level: Level
    tags: list[str]
    published: bool
    owner_username: str
    is_owner: bool
    lesson_count: int
    enrolment_count: int
    enrolled: bool
    progress_percent: int
    created_at: UtcDatetime


class CourseDetail(CourseSummary):
    lessons: list[LessonOutline]


class CoursePage(BaseModel):
    items: list[CourseSummary]
    next_cursor: int | None


class EnrollmentOut(BaseModel):
    course_id: int
    enrolled_at: UtcDatetime


class ProgressOut(BaseModel):
    course_id: int
    total_lessons: int
    completed_lesson_ids: list[int]
    percent: int
    quizzes_total: int
    quizzes_passed: int
    completed: bool


class CertificateOut(BaseModel):
    learner: str
    course: str
    completed_at: UtcDatetime
    code: str


class PublicCertificateOut(BaseModel):
    learner: str
    course: str
    completed_at: UtcDatetime
