from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import MAX_LIST_ITEMS, get_posting, get_visible_posting, require_owner
from app.db import get_db
from app.models import Application, Posting, Profile
from app.schemas import (
    ApplicantOut,
    ApplicationCreate,
    ApplicationOut,
    ApplicationStatusUpdate,
)
from app.serializers import applicant_out, application_out, is_expired
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

# Employer-driven status transitions; hired and rejected are terminal.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "submitted": frozenset({"reviewing", "shortlisted", "rejected"}),
    "reviewing": frozenset({"shortlisted", "rejected", "hired"}),
    "shortlisted": frozenset({"hired", "rejected"}),
    "hired": frozenset(),
    "rejected": frozenset(),
}


def _get_application(db: Session, application_id: int) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return application


@router.post(
    "/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED
)
def apply(
    job_id: int,
    body: ApplicationCreate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    posting = get_visible_posting(db, job_id, user)
    if posting.owner_id == user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot apply to your own posting")
    if is_expired(posting):
        raise HTTPException(status.HTTP_409_CONFLICT, "This posting has expired")
    already = db.scalar(
        select(Application.id).where(
            Application.posting_id == posting.id, Application.applicant_id == user.user_id
        )
    )
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already applied to this job")
    application = Application(
        posting_id=posting.id,
        applicant_id=user.user_id,
        applicant_username=user.username,
        **body.model_dump(),
    )
    db.add(application)
    try:
        db.commit()
    except IntegrityError:  # concurrent duplicate; the unique constraint is the real guard
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already applied to this job") from None
    return application_out(application, posting)


@router.get("/me/applications", response_model=list[ApplicationOut])
def my_applications(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ApplicationOut]:
    rows = db.execute(
        select(Application, Posting)
        .join(Posting, Posting.id == Application.posting_id)
        .where(Application.applicant_id == user.user_id)
        .order_by(Application.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return [application_out(application, posting) for application, posting in rows]


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_application(
    application_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    application = _get_application(db, application_id)
    if application.applicant_id != user.user_id:  # 404, not 403: do not reveal other users' ids
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if application.status == "hired":
        raise HTTPException(status.HTTP_409_CONFLICT, "A hired application cannot be withdrawn")
    db.delete(application)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}/applications", response_model=list[ApplicantOut])
def list_applicants(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApplicantOut]:
    posting = require_owner(get_posting(db, job_id), user)
    rows = db.execute(
        select(Application, Profile)
        .outerjoin(Profile, Profile.user_id == Application.applicant_id)
        .where(Application.posting_id == posting.id)
        .order_by(Application.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return [applicant_out(application, profile) for application, profile in rows]


@router.patch("/applications/{application_id}", response_model=ApplicantOut)
def update_application(
    application_id: int,
    body: ApplicationStatusUpdate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicantOut:
    application = _get_application(db, application_id)
    require_owner(get_posting(db, application.posting_id), user)
    if body.status != application.status and (
        body.status not in ALLOWED_TRANSITIONS.get(application.status, frozenset())
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot move an application from {application.status} to {body.status}",
        )
    application.status = body.status
    if body.note is not None:
        application.employer_note = body.note
    db.commit()
    profile = db.get(Profile, application.applicant_id)
    return applicant_out(application, profile)
