from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.access import MAX_LIST_ITEMS, get_posting, get_visible_posting, require_owner
from app.db import get_db
from app.models import Application, Posting, SavedJob, pack_tags
from app.queries import CURSOR_PATTERN, SearchParams, search_postings
from app.schemas import (
    LOCATION_MAX,
    TAG_MAX,
    TAG_PATTERN,
    EmploymentType,
    PostingCreate,
    PostingDetail,
    PostingPage,
    PostingSummary,
    PostingUpdate,
    check_salary_range,
)
from app.serializers import detail, summaries
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

MAX_OPEN_POSTINGS_PER_USER = 50
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_QUERY_LENGTH = 100

router = APIRouter()


@router.post("/jobs", response_model=PostingDetail, status_code=status.HTTP_201_CREATED)
def create_posting(
    body: PostingCreate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostingDetail:
    open_count = db.scalar(
        select(func.count()).select_from(Posting).where(
            Posting.owner_id == user.user_id, Posting.status == "open"
        )
    )
    if (open_count or 0) >= MAX_OPEN_POSTINGS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, "Too many open postings; close one first")
    posting = Posting(
        owner_id=user.user_id,
        owner_username=user.username,
        **body.model_dump(exclude={"tags"}),
        tags_text=pack_tags(body.tags),
    )
    db.add(posting)
    db.commit()
    return detail(db, user, posting)


@router.get("/jobs", response_model=PostingPage)
def list_postings(
    q: Annotated[str | None, Query(max_length=MAX_QUERY_LENGTH)] = None,
    location: Annotated[str | None, Query(max_length=LOCATION_MAX)] = None,
    remote: bool | None = None,
    type: EmploymentType | None = None,
    min_salary: Annotated[int | None, Query(ge=0)] = None,
    tag: Annotated[str | None, Query(max_length=TAG_MAX, pattern=TAG_PATTERN)] = None,
    cursor: Annotated[str | None, Query(pattern=CURSOR_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostingPage:
    params = SearchParams(
        q=q.strip() if q else None,
        location=location.strip() if location else None,
        remote=remote,
        employment_type=type,
        min_salary=min_salary,
        tag=tag.lower() if tag else None,
        cursor=cursor,
        limit=limit,
    )
    postings, next_cursor = search_postings(db, params)
    return PostingPage(items=summaries(db, user, postings), next_cursor=next_cursor)


@router.get("/me/postings", response_model=list[PostingSummary])
def my_postings(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PostingSummary]:
    postings = db.scalars(
        select(Posting)
        .where(Posting.owner_id == user.user_id)
        .order_by(Posting.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return summaries(db, user, list(postings))


@router.get("/jobs/{job_id}", response_model=PostingDetail)
def read_posting(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostingDetail:
    return detail(db, user, get_visible_posting(db, job_id, user))


@router.patch("/jobs/{job_id}", response_model=PostingDetail)
def update_posting(
    job_id: int,
    body: PostingUpdate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostingDetail:
    posting = require_owner(get_posting(db, job_id), user)
    changes = body.model_dump(exclude_unset=True)
    if "tags" in changes:
        changes["tags_text"] = pack_tags(changes.pop("tags"))
    salary_min = changes.get("salary_min", posting.salary_min)
    salary_max = changes.get("salary_max", posting.salary_max)
    try:
        check_salary_range(salary_min, salary_max)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    for field, value in changes.items():
        setattr(posting, field, value)
    db.commit()
    return detail(db, user, posting)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_posting(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    posting = require_owner(get_posting(db, job_id), user)
    db.execute(delete(Application).where(Application.posting_id == posting.id))
    db.execute(delete(SavedJob).where(SavedJob.posting_id == posting.id))
    db.delete(posting)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
