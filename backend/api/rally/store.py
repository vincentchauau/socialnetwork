"""Matches and rallies in the database. Every read and write is limited to the matches of the signed-in person."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.rally.models import Match

import logging
logger = logging.getLogger(__name__)


def owned_match(db: Session, user_id: int, match_id: int) -> Match:
    """The match when it belongs to the person; 404 otherwise (a match of someone else is not revealed)."""
    try:
        match = db.scalars(select(Match).where(Match.id == match_id, Match.user_id == user_id)).first()
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")
        return match
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("owned_match failed")
        raise


def list_matches(db: Session, user_id: int) -> list[Match]:
    try:
        return list(db.scalars(select(Match).where(Match.user_id == user_id).order_by(Match.id.desc())).all())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_matches failed")
        raise
