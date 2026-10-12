"""Per-user resources: saved jobs and the candidate profile."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import MAX_LIST_ITEMS, get_visible_posting
from app.db import get_db
from app.models import Posting, Profile, SavedJob
from app.queries import is_visible, now_utc
from app.schemas import PostingSummary, ProfileIn, ProfileOut
from app.serializers import profile_out, summaries
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()


@router.put("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def save_job(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    posting = get_visible_posting(db, job_id, user)
    if db.get(SavedJob, (user.user_id, posting.id)) is None:
        db.add(SavedJob(user_id=user.user_id, posting_id=posting.id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def unsave_job(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    saved = db.get(SavedJob, (user.user_id, job_id))
    if saved is not None:
        db.delete(saved)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/saved", response_model=list[PostingSummary])
def my_saved(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[PostingSummary]:
    postings = db.scalars(
        select(Posting)
        .join(SavedJob, SavedJob.posting_id == Posting.id)
        .where(SavedJob.user_id == user.user_id, is_visible(now_utc()))
        .order_by(SavedJob.created_at.desc(), Posting.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return summaries(db, user, list(postings))


@router.get("/me/profile", response_model=ProfileOut)
def read_profile(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProfileOut:
    profile = db.get(Profile, user.user_id)
    if profile is None:
        return ProfileOut(username=user.username, **ProfileIn().model_dump())
    return profile_out(profile)


@router.put("/me/profile", response_model=ProfileOut)
def write_profile(
    body: ProfileIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = db.get(Profile, user.user_id)
    if profile is None:
        profile = Profile(user_id=user.user_id)
        db.add(profile)
    profile.username = user.username
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    db.commit()
    return profile_out(profile)
