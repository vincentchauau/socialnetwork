"""Account management for the signed-in user (all state changes need X-CSRF-Token)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import AuthSession, check_origin, client_ip, csrf_session, require_reauth, settings_of
from app.models import User
from app.passwords import hash_password, password_problem
from app.routes_auth import me_out, verify_google_or_throttle
from app.schemas import ChangePasswordBody, DeleteAccountBody, LinkGoogleBody, MeOut, SessionOut
from app.sessions import clear_session_cookies, issue_session

router = APIRouter(prefix="/auth/me", tags=["account"], dependencies=[Depends(check_origin)])

GOOGLE_IN_USE = "That Google account is already linked to an account"


@router.post("/password", response_model=SessionOut)
def change_password(
    body: ChangePasswordBody,
    request: Request,
    response: Response,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> SessionOut:
    user = session.user
    # Google-only accounts may set a first password without one; every other session is revoked below.
    require_reauth(request, user, body.current_password)
    problem = password_problem(body.new_password, user.username)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # revokes all other sessions and refresh tokens
    db.commit()
    audit.info("password changed user=%r ip=%s", user.username, client_ip(request))
    return issue_session(response, user, settings_of(request))


@router.post("/google", response_model=MeOut)
def link_google(
    body: LinkGoogleBody,
    request: Request,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> MeOut:
    user = session.user
    require_reauth(request, user, body.password)
    identity = verify_google_or_throttle(request, body.id_token)
    if db.scalar(select(User.id).where(User.google_sub == identity.sub)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, GOOGLE_IN_USE)
    user.google_sub = identity.sub
    if user.email is None and db.scalar(select(User.id).where(User.email == identity.email)) is None:
        user.email = identity.email
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, GOOGLE_IN_USE) from None
    audit.info("google linked user=%r ip=%s", user.username, client_ip(request))
    return me_out(user, session.token)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: Request,
    response: Response,
    body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> None:
    user = session.user
    require_reauth(request, user, body.password if body else None)
    username = user.username
    db.delete(user)
    db.commit()
    clear_session_cookies(response, settings_of(request))
    audit.info("account deleted user=%r ip=%s", username, client_ip(request))
