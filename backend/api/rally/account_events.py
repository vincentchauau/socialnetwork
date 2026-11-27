"""Reactions to account events published by `center` (delivered at least once).

Data model: `rally_matches` (user_id, name, the video file) and `rally_rallies` (the rallies of a match, deleted with it).

Deletion: the matches and their rallies are deleted, and so are their video files.
Rename: nothing to do (the matches keep no name of the person).
Both handlers are idempotent, never raise for missing data and never commit.
"""

from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.rally.models import Match, Rally

import logging
logger = logging.getLogger(__name__)


def on_user_deleted(db: Session, user_id: int) -> None:
    try:
        matches = list(db.scalars(select(Match).where(Match.user_id == user_id)).all())
        for match in matches:
            db.execute(delete(Rally).where(Rally.match_id == match.id))
            Path(match.video_path).unlink(missing_ok=True)
            db.delete(match)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_deleted failed")
        raise


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """Nothing to do: matches keep no name of the person."""
