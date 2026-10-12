from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import ColumnElement, and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models import Application, Posting, SavedJob

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
    cursor: str | None = None
    limit: int = 20


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_visible(now: datetime) -> ColumnElement[bool]:
    """Open and not past its expiry date."""
    return and_(
        Posting.status == "open",
        or_(Posting.expires_at.is_(None), Posting.expires_at > now),
    )


def relevance(q: str | None) -> ColumnElement[int]:
    if not q:
        return literal(0)
    return (
        case((Posting.title.icontains(q, autoescape=True), TITLE_WEIGHT), else_=0)
        + case((Posting.tags_text.icontains(q, autoescape=True), TAG_WEIGHT), else_=0)
        + case((Posting.description.icontains(q, autoescape=True), DESCRIPTION_WEIGHT), else_=0)
    )


def _filters(params: SearchParams, now: datetime, score: ColumnElement[int]) -> list:
    conditions = [is_visible(now)]
    if params.q:
        conditions.append(score > 0)
    if params.location:
        conditions.append(Posting.location.icontains(params.location, autoescape=True))
    if params.remote is not None:
        conditions.append(Posting.remote.is_(params.remote))
    if params.employment_type:
        conditions.append(Posting.employment_type == params.employment_type)
    if params.min_salary is not None:
        conditions.append(
            func.coalesce(Posting.salary_max, Posting.salary_min) >= params.min_salary
        )
    if params.tag:
        conditions.append(Posting.tags_text.contains(f",{params.tag},", autoescape=True))
    return conditions


def _after_cursor(cursor: str, score: ColumnElement[int]) -> ColumnElement[bool]:
    last_score, last_id = (int(part) for part in cursor.split(":"))
    return or_(score < last_score, and_(score == last_score, Posting.id < last_id))


def search_postings(
    db: Session, params: SearchParams
) -> tuple[list[Posting], str | None]:
    """Open, unexpired postings ranked by relevance then recency, plus the next cursor."""
    score = relevance(params.q)
    conditions = _filters(params, now_utc(), score)
    if params.cursor:
        conditions.append(_after_cursor(params.cursor, score))
    statement = (
        select(Posting, score.label("score"))
        .where(*conditions)
        .order_by(score.desc(), Posting.id.desc())
        .limit(params.limit + 1)
    )
    rows = db.execute(statement).all()
    page = rows[: params.limit]
    next_cursor = None
    if len(rows) > params.limit:
        last_posting, last_score = page[-1]
        next_cursor = f"{int(last_score)}:{last_posting.id}"
    return [posting for posting, _ in page], next_cursor


def application_counts(db: Session, posting_ids: list[int]) -> dict[int, int]:
    if not posting_ids:
        return {}
    rows = db.execute(
        select(Application.posting_id, func.count())
        .where(Application.posting_id.in_(posting_ids))
        .group_by(Application.posting_id)
    ).all()
    return {posting_id: count for posting_id, count in rows}


def applied_ids(db: Session, user_id: int, posting_ids: list[int]) -> set[int]:
    if not posting_ids:
        return set()
    return set(
        db.scalars(
            select(Application.posting_id).where(
                Application.applicant_id == user_id, Application.posting_id.in_(posting_ids)
            )
        )
    )


def saved_ids(db: Session, user_id: int, posting_ids: list[int]) -> set[int]:
    if not posting_ids:
        return set()
    return set(
        db.scalars(
            select(SavedJob.posting_id).where(
                SavedJob.user_id == user_id, SavedJob.posting_id.in_(posting_ids)
            )
        )
    )
