"""The profile of the signed-in user: read it, change any part of it (a state change needs X-CSRF-Token)."""

from fastapi import APIRouter, Depends
from sn_shared import skills
from sqlalchemy.orm import Session

from api.center.db import get_db
from api.center.deps import AuthSession, check_origin, csrf_session, current_session
from api.center.profile import ProfileBody, ProfileOut, apply_profile, profile_out

router = APIRouter(prefix="/auth/me/profile", tags=["profile"], dependencies=[Depends(check_origin)])


@router.get("", response_model=ProfileOut)
def read_profile(session: AuthSession = Depends(current_session)) -> ProfileOut:
    return profile_out(session.user)


@router.put("", response_model=ProfileOut)
def change_profile(
    body: ProfileBody,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> ProfileOut:
    """Partial update: only the fields sent change. The profile holds no credential, so no re-authentication."""
    apply_profile(session.user, body)
    if body.skills:  # the skills of a person are in the vocabulary that jobs and courses share (`sn_shared.skills`)
        skills.register(db, [item.name for item in body.skills])
    db.commit()
    db.refresh(session.user)
    return profile_out(session.user)
