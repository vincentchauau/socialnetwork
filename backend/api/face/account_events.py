"""Reactions to account events published by `center` (delivered at least once).

Deletion removes all of the user's measurements. No username is stored, so a
rename needs nothing. Handlers are idempotent and never commit.
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.face.models import Measurement

import logging
logger = logging.getLogger(__name__)


def on_user_deleted(db: Session, user_id: int) -> None:
    try:
        if user_id <= 0:
            return
        db.execute(delete(Measurement).where(Measurement.user_id == user_id))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_deleted failed")
        raise


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    try:
        return None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_renamed failed")
        raise
