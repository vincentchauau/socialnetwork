"""Reactions to account events published by `center` (delivered at least once).

Data model: `job_descriptions` (owner_id) and `job_applicants` (user_id: the jobs a person
saved and applied to, with the steps of each application, cover letter, resume and contact email).

Deletion:
- DELETED: the rows of the user in `job_applicants` (personal data including resume and contact email).
- ANONYMIZED, rows kept: the jobs owned by the user. Applicants hold applications against them, so deleting would
  destroy other people's history: owner_id -> tombstone 0 (center ids start at 1) (the name is read from
  `users`, so the tombstone reads as DELETED_USERNAME) and status -> "closed" so no new applications arrive.

Rename does nothing: names are read from `users` of center (sn_shared.directory).

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from sn_shared import comments

from api.job.models import JobApplicant, JobDescription

import logging
logger = logging.getLogger(__name__)

DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    try:
        if user_id == DELETED_USER_ID:
            return
        db.execute(delete(JobApplicant).where(JobApplicant.user_id == user_id))
        comments.forget_user(db, user_id, ["job"])
        db.execute(
            update(JobDescription)
            .where(JobDescription.owner_id == user_id)
            .values(owner_id=DELETED_USER_ID, status="closed")
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_deleted failed")
        raise


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """Nothing to do: rows keep only the id, the name is read from `users`."""
