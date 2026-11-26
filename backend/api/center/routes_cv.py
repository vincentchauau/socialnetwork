"""The CV of a person: read it (its owner sees all of it, others what the visibility of each part allows)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.center.db import get_db
from api.center.deps import check_origin, current_session
from api.center.models import User
from api.center.profile import CvOut, cv_of

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/cv", tags=["cv"], dependencies=[Depends(check_origin)])


def viewer(request: Request, db: Session, owner_id: int) -> str:
    """"owner" for the person themselves, "employer" for any other signed-in person, "anyone" otherwise."""
    try:
        session = current_session(request, db)
    except HTTPException:
        return "anyone"
    return "owner" if session.user.id == owner_id else "employer"


@router.get("/{username}", response_model=CvOut)
def read_cv(username: str, request: Request, db: Session = Depends(get_db)) -> CvOut:
    try:
        person = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
        if person is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person")
        return cv_of(person, viewer(request, db, person.id))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("read_cv failed")
        raise
