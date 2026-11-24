"""The jobs a person keeps to look at again: `saved` in their row of the job (see JobApplicant)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.job.access import MAX_LIST_ITEMS, get_visible_job_description
from api.job.db import get_db
from api.job.models import JobApplicant, JobDescription
from api.job.queries import is_visible, now_utc
from api.job.schemas import JobDescriptionSummary
from api.job.serializers import summaries
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()


@router.put("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def save_job(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    job = get_visible_job_description(db, job_id, user)
    row = db.scalars(
        select(JobApplicant).where(JobApplicant.job_description_id == job.id, JobApplicant.user_id == user.user_id)
    ).first()
    if row is None:
        row = JobApplicant(job_description_id=job.id, user_id=user.user_id)
        db.add(row)
    if not row.saved:
        row.saved = True
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/jobs/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def unsave_job(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.scalars(
        select(JobApplicant).where(JobApplicant.job_description_id == job_id, JobApplicant.user_id == user.user_id)
    ).first()
    if row is not None and row.saved:
        if row.status is None:  # nothing else is kept in the row
            db.delete(row)
        else:
            row.saved = False
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/saved", response_model=list[JobDescriptionSummary])
def my_saved(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[JobDescriptionSummary]:
    jobs = db.scalars(
        select(JobDescription)
        .join(JobApplicant, JobApplicant.job_description_id == JobDescription.id)
        .where(JobApplicant.user_id == user.user_id, JobApplicant.saved.is_(True), is_visible(now_utc()))
        .order_by(JobApplicant.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return summaries(db, user, list(jobs))
