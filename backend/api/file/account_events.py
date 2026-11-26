"""Reactions to account events published by `center` (delivered at least once).

Deletion removes the user's file sandbox, nothing else. Idempotent, ignores user_id <= 0. A rename needs nothing: no username is stored.
"""

from sqlalchemy.orm import Session

from api.file.store import erase_user

import logging
logger = logging.getLogger(__name__)


def on_user_deleted(db: Session, user_id: int) -> None:
    try:
        erase_user(user_id)
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
