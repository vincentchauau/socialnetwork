from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from sn_shared.access import ensure_owner  # noqa: F401  (a stranger gets 404: the rule of every app)
from sn_shared.security import TokenPayload

from api.job.models import JobDescription

import logging
logger = logging.getLogger(__name__)

MAX_LIST_ITEMS = 100


def get_job_description(db: Session, job_id: int) -> JobDescription:
    try:
        job = db.get(JobDescription, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        return job
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_job_description failed")
        raise


def get_visible_job_description(db: Session, job_id: int, user: TokenPayload) -> JobDescription:
    """A job the caller may see: any open one, or their own in any state."""
    try:
        job = get_job_description(db, job_id)
        if job.status != "open" and job.owner_id != user.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        return job
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_visible_job_description failed")
        raise

