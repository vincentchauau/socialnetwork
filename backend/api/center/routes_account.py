"""Account management for the signed-in user (all state changes need X-CSRF-Token)."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.center import usernames
from api.center.audit import audit
from api.center.events import USER_DELETED, USER_RENAMED, add_event
from api.center.db import get_db
from api.center.deps import AuthSession, check_origin, client_ip, csrf_session, ensure_reauth, settings_of, too_many
from api.center.methods import GOOGLE_IN_USE, KEEP_ONE, has_verified_email, methods_lost_on_unlink, usable_methods
from api.center.models import User
from api.center.notify import notify
from api.center.passwords import hash_password, password_problem
from api.center.routes_auth import me_out, verify_google_or_throttle
from api.center.models import utcnow
from api.center.schemas import ChangePasswordBody, DeleteAccountBody, LinkGoogleBody, MeOut, RenameBody, SessionOut
from api.center.sessions import clear_session_cookies, reissue_session
from api.center.tokenversion import bump_token_version, publish_token_version

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/me", tags=["account"], dependencies=[Depends(check_origin)])

GOOGLE_NOT_LINKED = "Google is not linked"
USERNAME_TAKEN = "Username already taken"  # also the register message: a reserved name looks taken
SAME_USERNAME = "That is already your username"


@router.post("/password", response_model=SessionOut)
def change_password(
    body: ChangePasswordBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> SessionOut:
    try:
        user = session.user
        # Google-only accounts may set a first password without one; every other session is revoked below.
        ensure_reauth(request, user, body.current_password)
        problem = password_problem(body.new_password)
        if problem:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
        user.password_hash = hash_password(body.new_password)
        settings = settings_of(request)
        bump_token_version(db, user, keep_sid=session.sid)  # revokes all other sessions and refresh tokens
        db.commit()
        publish_token_version(user, settings)
        audit.info("password changed user=%r ip=%s", user.username, client_ip(request))
        notify(request, background, user, "password_changed")
        return reissue_session(response, request, db, user, settings, session.sid)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("change_password failed")
        raise


@router.post("/google", response_model=MeOut)
def link_google(
    body: LinkGoogleBody,
    request: Request,
    background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> MeOut:
    user = session.user
    ensure_reauth(request, user, body.password)
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
    try:
        user = session.user
        ensure_reauth(request, user, body.password if body else None)
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
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("unlink_google failed")
        raise


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    request: Request,
    response: Response,
    background: BackgroundTasks,
    body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> None:
    try:
        user = session.user
        ensure_reauth(request, user, body.password if body else None)
        username = user.username
        notice_to = user.email if has_verified_email(user) else None
        settings = settings_of(request)
        user_id = user.id
        add_event(db, USER_DELETED, user_id, {"old_username": username})  # same transaction as the delete
        usernames.reserve(db, username, user_id)  # nobody can impersonate the old name for 30 days
        bump_token_version(db, user)  # every access token and refresh token of the account ends, in every app
        min_version = user.token_version
        db.delete(user)
        db.commit()
        publish_token_version(user_id, settings, min_version)
        background.add_task(request.app.state.event_relay.publish_pending)
        clear_session_cookies(response, settings)
        audit.info("account deleted user=%r ip=%s", username, client_ip(request))
        if notice_to:
            notify(request, background, user, "account_deleted", to=notice_to)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("delete_account failed")
        raise


def too_soon(after) -> HTTPException:
    try:
        when = f" after {after.date().isoformat()}" if after is not None else " later"
        return HTTPException(status.HTTP_409_CONFLICT, f"Username can be changed again{when}")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("too_soon failed")
        raise


@router.post("/username", response_model=SessionOut)
def change_username(
    body: RenameBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> SessionOut:
    """Rename the account: once per 30 days, the old name stays reserved for its owner for 30 days.

    Apps keep copies of the name, so the change travels as a `user.renamed` event written in this transaction.
    The token_version is bumped (other sessions end) and this session gets a token with the new name.
    """
    user = session.user
    if not request.app.state.rename_throttle.check_and_record(str(user.id)):
        raise too_many()
    ensure_reauth(request, user, body.password)
    old, new = user.username, body.username
    if new == old:  # exactly the same text; a capitalisation-only change is a (counted) rename
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, SAME_USERNAME)
    # Row lock (PostgreSQL) and a fresh read, so two concurrent renames serialise; the conditional UPDATE
    # below is the backstop everywhere (SQLite has no row locks).
    db.execute(select(User.id).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    db.refresh(user)
    allowed_after = usernames.can_rename_after(user)
    if allowed_after is not None:
        raise too_soon(allowed_after)
    if usernames.unavailable(db, new, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, USERNAME_TAKEN)
    notice_to = user.email if has_verified_email(user) else None
    usernames.release(db, new)  # switching back to a name of its own
    usernames.reserve(db, old, user.id)
    now = utcnow()
    claimed = db.execute(
        update(User)
        .where(User.id == user.id, or_(User.username_changed_at.is_(None), User.username_changed_at <= now - usernames.RENAME_INTERVAL))
        .values(username=new, username_changed_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:  # a concurrent rename won
        db.rollback()
        raise too_soon(None)
    db.refresh(user, ["username", "username_changed_at"])
    add_event(db, USER_RENAMED, user.id, {"username": new, "old_username": old}, with_seq=True)
    bump_token_version(db, user, keep_sid=session.sid)  # other sessions end; this one is re-issued below
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, USERNAME_TAKEN) from None
    settings = settings_of(request)
    publish_token_version(user, settings)
    background.add_task(request.app.state.event_relay.publish_pending)
    audit.info("username changed user=%r old=%r ip=%s", new, old, client_ip(request))
    notify(request, background, user, "username_changed", to=notice_to, old_username=old, new_username=new)
    return reissue_session(response, request, db, user, settings, session.sid)
