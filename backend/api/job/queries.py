import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import ColumnElement, String, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from sn_shared import skills

from api.job.models import JobApplicant, JobDescription

# Relevance weights: a title hit outranks a tag hit, which outranks a description hit.
TITLE_WEIGHT = 4
TAG_WEIGHT = 2
DESCRIPTION_WEIGHT = 1
CURSOR_PATTERN = r"^[0-9]:[0-9]{1,18}$"


@dataclass(frozen=True)
class SearchParams:
    q: str | None = None
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    min_salary: int | None = None
    tag: str | None = None
    skill: str | None = None
    cursor: str | None = None
    limit: int = 20


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_visible(now: datetime) -> ColumnElement[bool]:
    """Open and not past its expiry date."""
    return and_(
        JobDescription.status == "open",
        or_(JobDescription.expires_at.is_(None), JobDescription.expires_at > now),
    )


def relevance(q: str | None) -> ColumnElement[int]:
    if not q:
        return literal(0)
    return (
        case((JobDescription.title.icontains(q, autoescape=True), TITLE_WEIGHT), else_=0)
        + case((cast(JobDescription.tags, String).icontains(q, autoescape=True), TAG_WEIGHT), else_=0)
        + case((JobDescription.description.icontains(q, autoescape=True), DESCRIPTION_WEIGHT), else_=0)
    )


def _filters(params: SearchParams, now: datetime, score: ColumnElement[int]) -> list:
    conditions = [is_visible(now)]
    if params.q:
        conditions.append(score > 0)
    if params.location:
        conditions.append(JobDescription.location.icontains(params.location, autoescape=True))
    if params.remote is not None:
        conditions.append(JobDescription.remote.is_(params.remote))
    if params.employment_type:
        conditions.append(JobDescription.employment_type == params.employment_type)
    if params.min_salary is not None:
        conditions.append(
            func.coalesce(JobDescription.salary_max, JobDescription.salary_min) >= params.min_salary
        )
    if params.tag:
        conditions.append(cast(JobDescription.tags, String).contains(json.dumps(params.tag.strip().lower()), autoescape=True))
    if params.skill:  # asked for or only liked, however it is written
        conditions.append(cast(JobDescription.skill_keys, String).contains(json.dumps(skills.skill_key(params.skill)), autoescape=True))
    return conditions


def after_cursor(cursor: str, score: ColumnElement[int]) -> ColumnElement[bool]:
    last_score, last_id = (int(part) for part in cursor.split(":"))
    return or_(score < last_score, and_(score == last_score, JobDescription.id < last_id))


def search_job_descriptions(
    db: Session, params: SearchParams
) -> tuple[list[JobDescription], str | None]:
    """Open, unexpired jobs ranked by relevance then recency, plus the next cursor."""
    score = relevance(params.q)
    conditions = _filters(params, now_utc(), score)
    if params.cursor:
        conditions.append(after_cursor(params.cursor, score))
    statement = (
        select(JobDescription, score.label("score"))
        .where(*conditions)
        .order_by(score.desc(), JobDescription.id.desc())
        .limit(params.limit + 1)
    )
    rows = db.execute(statement).all()
    page = rows[: params.limit]
    next_cursor = None
    if len(rows) > params.limit:
        last_job, last_score = page[-1]
        next_cursor = f"{int(last_score)}:{last_job.id}"
    return [job for job, _ in page], next_cursor


def application_counts(db: Session, job_ids: list[int]) -> dict[int, int]:
    """How many people have applied to each job (a save alone is not an application)."""
    if not job_ids:
        return {}
    rows = db.execute(
        select(JobApplicant.job_description_id, func.count())
        .where(JobApplicant.job_description_id.in_(job_ids), JobApplicant.status.is_not(None))
        .group_by(JobApplicant.job_description_id)
    ).all()
    return {job_id: count for job_id, count in rows}


def my_rows(db: Session, user_id: int, job_ids: list[int]) -> dict[int, JobApplicant]:
    """The application of the person to each of these jobs, by job."""
    if not job_ids:
        return {}
    rows = db.scalars(
        select(JobApplicant).where(JobApplicant.user_id == user_id, JobApplicant.job_description_id.in_(job_ids))
    )
    return {row.job_description_id: row for row in rows}
