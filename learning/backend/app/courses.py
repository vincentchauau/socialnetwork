from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Course, CourseTag
from app.schemas import (
    TAG_MAX,
    CourseDetail,
    CourseIn,
    CoursePage,
    CoursePatch,
    CourseSummary,
    Level,
)
from app.services import (
    build_detail,
    build_summaries,
    optional_user,
    owned_course,
    visible_course,
)
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

MAX_COURSES_PER_USER = 50
LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 50
SEARCH_MAX = 100
ESCAPE_CHAR = "\\"


def _like_pattern(text: str) -> str:
    escaped = (
        text.replace(ESCAPE_CHAR, ESCAPE_CHAR * 2).replace("%", ESCAPE_CHAR + "%").replace("_", ESCAPE_CHAR + "_")
    )
    return f"%{escaped}%"


def _sync_tags(course: Course, wanted: list[str]) -> None:
    """Add missing tags and drop removed ones (no delete+insert of the same row)."""
    target = set(wanted)
    course.tags = [tag for tag in course.tags if tag.tag in target]
    existing = {tag.tag for tag in course.tags}
    course.tags.extend(CourseTag(tag=name) for name in sorted(target - existing))


@router.post("/courses", status_code=status.HTTP_201_CREATED, response_model=CourseDetail)
def create_course(
    body: CourseIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseDetail:
    owned = db.scalar(select(func.count()).select_from(Course).where(Course.owner_id == user.user_id))
    if (owned or 0) >= MAX_COURSES_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, "Course limit reached")
    course = Course(
        owner_id=user.user_id,
        owner_username=user.username,
        title=body.title,
        summary=body.summary,
        level=body.level,
        published=body.published,
    )
    _sync_tags(course, body.tags)
    db.add(course)
    db.commit()
    db.expire_all()
    return build_detail(db, course, user)


@router.get("/courses", response_model=CoursePage)
def list_courses(
    q: Annotated[str | None, Query(max_length=SEARCH_MAX)] = None,
    level: Level | None = None,
    tag: Annotated[str | None, Query(max_length=TAG_MAX)] = None,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_MAX_LIMIT)] = LIST_DEFAULT_LIMIT,
    user: TokenPayload | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> CoursePage:
    stmt = select(Course).where(Course.published.is_(True))
    if q:
        pattern = _like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Course.title.ilike(pattern, escape=ESCAPE_CHAR),
                Course.summary.ilike(pattern, escape=ESCAPE_CHAR),
            )
        )
    if level:
        stmt = stmt.where(Course.level == level)
    if tag:
        tagged = select(CourseTag.course_id).where(CourseTag.tag == tag.strip().lower())
        stmt = stmt.where(Course.id.in_(tagged))
    if cursor:
        stmt = stmt.where(Course.id < cursor)
    rows = list(db.scalars(stmt.order_by(Course.id.desc()).limit(limit + 1)))
    page, has_more = rows[:limit], len(rows) > limit
    return CoursePage(
        items=build_summaries(db, page, user),
        next_cursor=page[-1].id if has_more else None,
    )


@router.get("/me/authored", response_model=list[CourseSummary])
def my_authored(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CourseSummary]:
    courses = list(
        db.scalars(select(Course).where(Course.owner_id == user.user_id).order_by(Course.id.desc()))
    )
    return build_summaries(db, courses, user)


@router.get("/courses/{course_id}", response_model=CourseDetail)
def get_course(
    course_id: int,
    user: TokenPayload | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> CourseDetail:
    return build_detail(db, visible_course(db, course_id, user), user)


@router.patch("/courses/{course_id}", response_model=CourseDetail)
def update_course(
    course_id: int,
    body: CoursePatch,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseDetail:
    course = owned_course(db, course_id, user)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    tags = changes.pop("tags", None)
    for field, value in changes.items():
        setattr(course, field, value)
    if tags is not None:
        _sync_tags(course, tags)
    db.commit()
    db.expire_all()
    return build_detail(db, course, user)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(owned_course(db, course_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
