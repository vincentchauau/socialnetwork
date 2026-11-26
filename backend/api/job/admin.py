"""Admin CRUD (`/admin`) and the person's own twin (`/data`) for the job tables (see `sn_shared.admincrud`).

Deleting a job description through the generic route would orphan its applicants, tags, skills and comments, so
both mounts run the same `on_delete` as `DELETE /jobs/{id}`.

For a person (`/data`): their own job descriptions (CRUD); the applicants of their own jobs and their own
applications (read), where they may add or withdraw (delete) their own row. `status`, `history`, `resume` and
`employer_note` are not writable by a person (an application is made through the app), and `employer_note` is not
shown. The employer sees only rows that were applied for, not rows somebody merely saved.
"""

from fastapi import FastAPI, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.job.models import JobApplicant, JobDescription
from sn_shared import comments
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)


def delete_job_description(request: Request, db: Session, row, user: TokenPayload):
    try:
        job = db.get(JobDescription, row["id"])
        if job is None:
            return None
        db.execute(delete(JobApplicant).where(JobApplicant.job_description_id == job.id))
        comments.forget_object(db, "job", job.id)
        db.delete(job)
        return None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("delete_job_description failed")
        raise


def applicant_scope(db: Session, user: TokenPayload):
    """My own rows, plus the applications (not the mere saves) to jobs that are mine."""
    try:
        mine = select(JobDescription.id).where(JobDescription.owner_id == user.user_id)
        return (JobApplicant.user_id == user.user_id) | (
            JobApplicant.job_description_id.in_(mine) & JobApplicant.status.isnot(None)
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("applicant_scope failed")
        raise


SPECS = [
    TableSpec(JobDescription, owner="owner_id", on_delete=delete_job_description),
    TableSpec(
        JobApplicant,
        owner="user_id",
        scope=applicant_scope,
        user_readonly_columns=("status", "history", "resume", "employer_note"),
        user_hidden_columns=("employer_note",),
        refs={"job_description_id": ("job_descriptions", "title")}),
]


def mount(app: FastAPI) -> None:
    try:
        mount_crud(app, SPECS, database="job")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mount failed")
        raise
