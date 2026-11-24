from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.job.access import MAX_LIST_ITEMS, get_job_description, get_visible_job_description, ensure_owner
from api.job.db import get_db
from sn_shared import comments, skills as shared_skills

from api.job.models import JobApplicant, JobDescription
from api.job.queries import CURSOR_PATTERN, SearchParams, is_visible, now_utc, search_job_descriptions
from api.job.schemas import (
    LOCATION_MAX,
    SALARY_MAX_VALUE,
    TAG_MAX,
    TAG_PATTERN,
    EmploymentType,
    JobDescriptionCreate,
    JobDescriptionDetail,
    JobDescriptionPage,
    JobDescriptionSummary,
    JobDescriptionUpdate,
    check_salary_range,
)
from api.job.serializers import detail, summaries
from sn_shared.deps import get_current_user
from sn_shared.facets import Facet, facets
from sn_shared.security import TokenPayload

MAX_OPEN_JOBS_PER_USER = 50
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_QUERY_LENGTH = 100
# Lists are kept in the row as plain data; a skill is {name, level, years}.
LIST_FIELDS = ("skills_required", "skills_preferred", "languages")

router = APIRouter()


def _index_skills(db: Session, job: JobDescription) -> None:
    """The skills of the job go into the catalog (for suggestions) and their keys into the row (for search by skill)."""
    names = [item["name"] for item in (job.skills_required or []) + (job.skills_preferred or [])]
    shared_skills.register(db, names)
    job.skill_keys = shared_skills.keys_of(names)


def _plain(changes: dict) -> dict:
    """The lists of the job as the plain data that goes into the row."""
    plain = dict(changes)
    for name in LIST_FIELDS:
        if plain.get(name) is not None:
            plain[name] = [item if isinstance(item, dict) else item.model_dump() for item in plain[name]]
    return plain


@router.post("/jobs", response_model=JobDescriptionDetail, status_code=status.HTTP_201_CREATED)
def create_job_description(
    body: JobDescriptionCreate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescriptionDetail:
    open_count = db.scalar(
        select(func.count()).select_from(JobDescription).where(
            JobDescription.owner_id == user.user_id, JobDescription.status == "open"
        )
    )
    if body.status == "open" and (open_count or 0) >= MAX_OPEN_JOBS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many open jobs; close one first")
    fields = _plain(body.model_dump())
    job = JobDescription(owner_id=user.user_id, **fields)
    db.add(job)
    db.flush()
    _index_skills(db, job)
    db.commit()
    return detail(db, user, job)


@router.get("/jobs", response_model=JobDescriptionPage)
def list_job_descriptions(
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
    location: Annotated[str | None, Query(max_length=LOCATION_MAX)] = None,
    remote: bool | None = None,
    type: EmploymentType | None = None,
    min_salary: Annotated[int | None, Query(ge=0, le=SALARY_MAX_VALUE)] = None,
    tag: Annotated[str | None, Query(max_length=TAG_MAX, pattern=TAG_PATTERN)] = None,
    skill: Annotated[str | None, Query(max_length=shared_skills.NAME_MAX)] = None,
    cursor: Annotated[str | None, Query(pattern=CURSOR_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescriptionPage:
    params = SearchParams(
        q=q.strip() if q else None,
        location=location.strip() if location else None,
        remote=remote,
        employment_type=type,
        min_salary=min_salary,
        tag=tag.lower() if tag else None,
        skill=skill.strip() if skill and skill.strip() else None,
        cursor=cursor,
        limit=limit,
    )
    jobs, next_cursor = search_job_descriptions(db, params)
    return JobDescriptionPage(items=summaries(db, user, jobs), next_cursor=next_cursor)


@router.get("/facets", response_model=dict[str, list[Facet]])
def job_facets(
    _user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, list[Facet]]:
    """What the open jobs are made of: how many of each employment type and of each place."""
    open_now = select(JobDescription).where(is_visible(now_utc()))
    return {
        "types": facets(db, JobDescription.employment_type, open_now),
        "locations": facets(db, JobDescription.location, open_now),
    }


@router.get("/me/jobs", response_model=list[JobDescriptionSummary])
def my_job_descriptions(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[JobDescriptionSummary]:
    jobs = db.scalars(
        select(JobDescription)
        .where(JobDescription.owner_id == user.user_id)
        .order_by(JobDescription.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return summaries(db, user, list(jobs))


@router.get("/jobs/{job_id}", response_model=JobDescriptionDetail)
def read_job_description(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescriptionDetail:
    return detail(db, user, get_visible_job_description(db, job_id, user))


@router.patch("/jobs/{job_id}", response_model=JobDescriptionDetail)
def update_job_description(
    job_id: int,
    body: JobDescriptionUpdate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDescriptionDetail:
    job = ensure_owner(get_job_description(db, job_id), user)
    changes = _plain(body.model_dump(exclude_unset=True))
    salary_min = changes.get("salary_min", job.salary_min)
    salary_max = changes.get("salary_max", job.salary_max)
    try:
        check_salary_range(salary_min, salary_max)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    for field, value in changes.items():
        setattr(job, field, value)
    if "skills_required" in changes or "skills_preferred" in changes:
        _index_skills(db, job)
    db.commit()
    return detail(db, user, job)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_description(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    job = ensure_owner(get_job_description(db, job_id), user)
    db.execute(delete(JobApplicant).where(JobApplicant.job_description_id == job.id))
    comments.forget_object(db, "job", job.id)
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
