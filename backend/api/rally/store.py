"""Matches and rallies in the database. Every read and write is limited to the matches of the signed-in person."""

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api.rally.models import Match, Rally
from api.rally.schemas import RallyIn

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


def list_rallies(db: Session, match_id: int) -> list[Rally]:
    try:
        return list(db.scalars(select(Rally).where(Rally.match_id == match_id).order_by(Rally.number)).all())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_rallies failed")
        raise


def add_rally(db: Session, match_id: int, body: RallyIn) -> Rally:
    """Append a rally; it takes the next number of the match."""
    try:
        last = db.scalar(select(func.max(Rally.number)).where(Rally.match_id == match_id)) or 0
        rally = Rally(match_id=match_id, number=last + 1, **body.model_dump())
        db.add(rally)
        db.flush()
        return rally
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_rally failed")
        raise


def delete_rally(db: Session, match_id: int, rally_id: int) -> bool:
    try:
        result = db.execute(delete(Rally).where(Rally.id == rally_id, Rally.match_id == match_id))
        return result.rowcount > 0
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("delete_rally failed")
        raise
