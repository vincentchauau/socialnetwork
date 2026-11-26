"""Who has applied to a job, and where each application is: the steps are kept in the row of the person and the job."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sn_shared import directory

from api.job.access import MAX_LIST_ITEMS, get_job_description, get_visible_job_description, ensure_owner
from api.job.db import get_db
from api.job.models import JobApplicant, JobDescription, utcnow
from api.job.schemas import ApplicantOut, ApplicationCreate, ApplicationOut, ApplicationStatusUpdate, MyApplicationEdit
from api.job.serializers import applicant_out, application_out, is_expired
from sn_shared.deps import get_current_user
from sn_shared.states import Transitions
from sn_shared.security import TokenPayload

router = APIRouter()

# Employer-driven steps; hired and rejected are terminal. An application starts at `submitted`.
APPLICATION_FLOW = Transitions({
    "submitted": ["reviewing", "shortlisted", "rejected"],
    "reviewing": ["shortlisted", "interview", "rejected", "hired"],
    "shortlisted": ["interview", "offer", "hired", "rejected"],
    "interview": ["offer", "hired", "rejected"],
    "offer": ["hired", "rejected"],
    "hired": [],
    "rejected": [],
})


def step(status_name: str, by: str) -> dict:
    return {"status": status_name, "at": utcnow().isoformat(), "by": by}


def get_application(db: Session, application_id: int) -> JobApplicant:
    row = db.get(JobApplicant, application_id)
    if row is None or row.status is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    return row


@router.post("/jobs/{job_id}/apply", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def apply(
    job_id: int,
    body: ApplicationCreate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    job = get_visible_job_description(db, job_id, user)
    if job.owner_id == user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot apply to your own job")
    if is_expired(job):
        raise HTTPException(status.HTTP_409_CONFLICT, "This job has expired")
    row = db.scalars(
        select(JobApplicant)
        .where(JobApplicant.job_description_id == job.id, JobApplicant.user_id == user.user_id)
        .with_for_update()
    ).first()
    if row is not None and row.status is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already applied to this job")
    if row is None:  # no row yet: a new one
        row = JobApplicant(job_description_id=job.id, user_id=user.user_id)
        db.add(row)
    fields = body.model_dump()
    row.cover_letter, row.resume, row.contact_email = fields["cover_letter"], fields["resume"], fields["contact_email"]
    row.status = "submitted"
    row.history = [step("submitted", "applicant")]
    try:
        db.commit()
    except IntegrityError:  # concurrent duplicate; the unique constraint is the real guard
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already applied to this job") from None
    return application_out(row, job)


@router.get("/me/applications", response_model=list[ApplicationOut])
def my_applications(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ApplicationOut]:
    rows = db.execute(
        select(JobApplicant, JobDescription)
        .join(JobDescription, JobDescription.id == JobApplicant.job_description_id)
        .where(JobApplicant.user_id == user.user_id, JobApplicant.status.is_not(None))
        .order_by(JobApplicant.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    return [application_out(row, job) for row, job in rows]


@router.patch("/applications/{application_id}/mine", response_model=ApplicationOut)
def edit_my_application(
    application_id: int,
    body: MyApplicationEdit,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    """The applicant changes their own application while the employer has not reviewed it yet (status "submitted")."""
    row = get_application(db, application_id)
    if row.user_id != user.user_id:  # someone else's application looks like none
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if row.status != "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an application that has not been reviewed can be changed")
    if body.cover_letter is not None:
        row.cover_letter = body.cover_letter
    if body.contact_email is not None:
        row.contact_email = body.contact_email
    db.commit()
    job = get_job_description(db, row.job_description_id)
    return application_out(row, job)


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_application(
    application_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = get_application(db, application_id)
    if row.user_id != user.user_id:  # 404, not 403: do not reveal other users' ids
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found")
    if row.status == "hired":
        raise HTTPException(status.HTTP_409_CONFLICT, "A hired application cannot be withdrawn")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/jobs/{job_id}/applications", response_model=list[ApplicantOut])
def list_applicants(
    job_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApplicantOut]:
    job = ensure_owner(get_job_description(db, job_id), user)
    rows = db.scalars(
        select(JobApplicant)
        .where(JobApplicant.job_description_id == job.id, JobApplicant.status.is_not(None))
        .order_by(JobApplicant.id.desc())
        .limit(MAX_LIST_ITEMS)
    ).all()
    found = directory.names(db, [row.user_id for row in rows])
    return [applicant_out(row, job, found[row.user_id]) for row in rows]


@router.patch("/applications/{application_id}", response_model=ApplicantOut)
def update_application(
    application_id: int,
    body: ApplicationStatusUpdate,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicantOut:
    row = get_application(db, application_id)
    job = ensure_owner(get_job_description(db, row.job_description_id), user)
    if body.status != row.status:
        APPLICATION_FLOW.check(row.status, body.status, "an application")
        row.history = [*(row.history or []), step(body.status, "employer")]
        row.status = body.status
    if body.note is not None:
        row.employer_note = body.note
    db.commit()
    return applicant_out(row, job, directory.name_of(db, row.user_id))
