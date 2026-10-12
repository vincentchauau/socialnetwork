"""Account management for the signed-in user (all state changes need X-CSRF-Token)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import AuthSession, check_origin, client_ip, csrf_session, require_reauth, settings_of
from app.methods import GOOGLE_IN_USE, KEEP_ONE, has_verified_email, methods_lost_on_unlink, usable_methods
from app.models import User
from app.notify import notify
from app.passwords import hash_password, password_problem
from app.routes_auth import me_out, verify_google_or_throttle
from app.schemas import ChangePasswordBody, DeleteAccountBody, LinkGoogleBody, MeOut, SessionOut
from app.sessions import clear_session_cookies, issue_session
from app.tokenversion import bump_token_version

router = APIRouter(prefix="/auth/me", tags=["account"], dependencies=[Depends(check_origin)])

GOOGLE_NOT_LINKED = "Google is not linked"


@router.post("/password", response_model=SessionOut)
def change_password(
    body: ChangePasswordBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
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
    bump_token_version(db, user)  # revokes all other sessions and refresh tokens
    db.commit()
    audit.info("password changed user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "password_changed")
    return issue_session(response, user, settings_of(request))


@router.post("/google", response_model=MeOut)
def link_google(
    body: LinkGoogleBody,
    request: Request,
    background: BackgroundTasks,
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
        user.email, user.email_verified = identity.email, True  # Google verified it
        user.email_from_google = True  # Google wrote it, so unlinking Google takes it away again
    elif user.email == identity.email:
        user.email_verified = True
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, GOOGLE_IN_USE) from None
    audit.info("google linked user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "google_linked")
    return me_out(user, session.token)


@router.delete("/google", response_model=MeOut)
def unlink_google(
    request: Request,
    background: BackgroundTasks,
    body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> MeOut:
    """Google may be dropped only while another sign-in method (password, voice, webcam) remains."""
    user = session.user
    require_reauth(request, user, body.password if body else None)
    if user.google_sub is None:
        raise HTTPException(status.HTTP_409_CONFLICT, GOOGLE_NOT_LINKED)
    # Unlinking clears the address only when Google supplied it; an address the user verified survives.
    if usable_methods(user, without=methods_lost_on_unlink(user)) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, KEEP_ONE)
    notice_to = user.email if has_verified_email(user) else None
    user.google_sub = None
    if user.email_from_google:
        user.email = None
        user.email_verified = False
        user.email_from_google = False
    db.commit()
    audit.info("google unlinked user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "google_unlinked", to=notice_to)
    return me_out(user, session.token)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: Request,
    response: Response,
    background: BackgroundTasks,
    body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> None:
    user = session.user
    require_reauth(request, user, body.password if body else None)
    username = user.username
    notice_to = user.email if has_verified_email(user) else None
    db.delete(user)
    db.commit()
    clear_session_cookies(response, settings_of(request))
    audit.info("account deleted user=%r ip=%s", username, client_ip(request))
    if notice_to:
        notify(request, background, user, "account_deleted", to=notice_to)
