"""Email: verify an address, sign in with a link or a code, forgot/reset password.

Rules that hold on every route here:
- tokens are consumed ONLY by POST (a mail scanner opening the link page burns nothing);
- the request routes answer the same 202 whether or not the address has an account;
- every failure of a link or a code is one generic 4xx, and submissions are throttled per address.
"""

import secrets
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.center import emailtokens as et
from api.center.audit import audit
from api.center.db import get_db
from api.center.deps import (
    AuthSession,
    biometrics_available,
    check_origin,
    client_ip,
    csrf_session,
    current_session,
    ensure_email,
    ensure_reauth,
    settings_of,
    too_many,
)
from api.center.mailer import mask_email
from api.center.methods import KEEP_ONE, has_verified_email, methods_status, usable_methods
from api.center.codes import EMAIL
from api.center.models import User, VerificationCode
from api.center.notify import notify, send_link_mail
from api.center.passwords import hash_password, password_problem
from api.center.schemas import (
    DeleteAccountBody,
    EmailBody,
    EmailCodeBody,
    EmailVerifiedOut,
    EmailVerifyBody,
    MethodsStatus,
    MfaRequired,
    OkOut,
    ResetBody,
    SessionOut,
    SetEmailBody,
    TokenBody,
)
from api.center.sessions import start_login
from api.center.tokenversion import bump_token_version, publish_token_version

import logging
logger = logging.getLogger(__name__)

BAD_LINK = "Invalid or expired link"
BAD_CODE = "Invalid or expired code"
EMAIL_TAKEN = "Email already in use"
MAX_JITTER_MS = 30

router = APIRouter(prefix="/auth", tags=["email"], dependencies=[Depends(ensure_email), Depends(check_origin)])


# --- shared helpers -------------------------------------------------------------------------------


def fail(code: int, detail: str) -> HTTPException:
    try:
        return HTTPException(code, detail)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("fail failed")
        raise


def gate_submit(request: Request) -> None:
    """Link/code submissions: per address, every one counts (the 429 depends on counters only)."""
    try:
        throttle, ip = request.app.state.email_submit_throttle, client_ip(request)
        if not throttle.check_and_record(ip):
            raise too_many()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("gate_submit failed")
        raise


def gate_request(request: Request, kind: str, address: str) -> None:
    """Mail requests, every one counts (known account or not): per IP, per (IP, normalised email) and per email.

    The pair counter stops one IP from spending the whole per-email budget, so a stranger cannot lock the owner out.
    """
    try:
        state, ip = request.app.state, client_ip(request)
        counters = {
            et.LOGIN: (state.email_login_ip_throttle, state.email_login_ip_addr_throttle, state.email_login_addr_throttle),
            et.RESET: (state.forgot_ip_throttle, state.forgot_ip_addr_throttle, state.forgot_addr_throttle),
            et.REAUTH: (state.reauth_mail_ip_throttle, state.reauth_mail_ip_addr_throttle, state.reauth_mail_addr_throttle),
        }[kind]
        keys = (ip, f"{ip}|{address}", address)
        if any(throttle.is_blocked(key) for throttle, key in zip(counters, keys)):
            raise too_many()
        for throttle, key in zip(counters, keys):
            throttle.record(key)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("gate_request failed")
        raise


def code_failure_key(address: str) -> str:
    try:
        return f"code|{address}"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("code_failure_key failed")
        raise


def guard_code_attempts(request: Request, key: str) -> None:
    """Failed code submissions per address across all rows (the 429 depends on the submitted string only)."""
    try:
        if request.app.state.email_code_fail_throttle.is_blocked(key):
            raise too_many()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("guard_code_attempts failed")
        raise


def count_code_failure(request: Request, key: str) -> None:
    try:
        request.app.state.email_code_fail_throttle.record(key)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("count_code_failure failed")
        raise


def jitter() -> None:
    """A small uniform random delay so the answer time does not tell a known address from an unknown one."""
    try:
        time.sleep(secrets.randbelow(MAX_JITTER_MS + 1) / 1000)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("jitter failed")
        raise


def verified_owner_id(db: Session, address: str) -> int | None:
    try:
        return db.scalar(select(User.id).where(User.email == address, User.email_verified.is_(True)))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("verified_owner_id failed")
        raise


def verified_user(db: Session, address: str) -> User | None:
    try:
        return db.scalar(select(User).where(User.email == address, User.email_verified.is_(True)))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("verified_user failed")
        raise


def drop_tokens(db: Session, user_id: int, purpose: str) -> None:
    try:
        db.execute(
            delete(VerificationCode)
            .where(VerificationCode.user_id == user_id, VerificationCode.channel == EMAIL, VerificationCode.purpose == purpose)
            .execution_options(synchronize_session=False)
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("drop_tokens failed")
        raise


def login_result(request: Request, response: Response, db: Session, user: User) -> SessionOut | MfaRequired:
    """Email is a primary factor: same hand-off as password and Google (the opt-in second factor applies)."""
    try:
        result = start_login(
            response, user, settings_of(request), biometrics_available(request), request=request, db=db, method="email"
        )
        audit.info("login %s (email) user=%r ip=%s", "mfa-pending" if isinstance(result, MfaRequired) else "ok",
                   user.username, client_ip(request))  # fmt: skip
        return result
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("login_result failed")
        raise


# --- add / verify / remove an address -------------------------------------------------------------


@router.post("/me/email", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def set_email(
    body: SetEmailBody, request: Request, background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> OkOut:  # fmt: skip
    """Start (or resend) verification of an address. `users.email` changes only when it is verified."""
    try:
        user, state = session.user, request.app.state
        user_throttle, target_throttle = state.email_change_throttle, state.email_change_target_throttle
        if user_throttle.is_blocked(str(user.id)) or target_throttle.is_blocked(body.email):
            raise too_many()
        ensure_reauth(request, user, body.password)
        user_throttle.record(str(user.id))
        target_throttle.record(body.email)  # per target address: this route cannot be used to mail-bomb a stranger
        owner = verified_owner_id(db, body.email)
        if owner is not None and owner != user.id:
            # Verified elsewhere: answer exactly like a success and send nothing, so the answer never says whose it is.
            et.issue(db, None, et.VERIFY, body.email, with_code=True)
            audit.info("email verification skipped (taken) user=%r ip=%s", user.username, client_ip(request))
            return OkOut()
        issued = et.issue(db, user, et.VERIFY, body.email, with_code=True)
        send_link_mail(request, background, et.VERIFY, body.email, issued.token, issued.code)
        audit.info("email verification requested user=%r email=%s ip=%s", user.username, mask_email(body.email),
                   client_ip(request))  # fmt: skip
        return OkOut()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("set_email failed")
        raise


@router.post("/email/verify", response_model=EmailVerifiedOut)
def verify_email(
    body: EmailVerifyBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> EmailVerifiedOut:
    """`{token}` (the link, public) or `{code}` (typed in the account: needs the session)."""
    gate_submit(request)
    failure_key = None
    if body.token:
        row, bad = et.find_by_token(db, body.token, et.VERIFY), BAD_LINK
        accepted = row is not None
    else:
        user = current_session(request, db).user
        failure_key = code_failure_key(f"user:{user.id}")  # the address is not submitted here: key by the account
        guard_code_attempts(request, failure_key)
        row, bad = et.find_for_user(db, user.id, et.VERIFY), BAD_CODE
        accepted = et.check_code(db, row, body.code or "")
    if not accepted or row is None:
        if failure_key:
            count_code_failure(request, failure_key)
        audit.warning("email verification failed ip=%s", client_ip(request))
        raise fail(status.HTTP_400_BAD_REQUEST, bad)
    owner = verified_owner_id(db, row.target)
    if owner is not None and owner != row.user_id:
        raise fail(status.HTTP_409_CONFLICT, EMAIL_TAKEN)  # verified elsewhere in the meantime
    user = db.get(User, row.user_id)
    if user is None or not et.consume(db, row.id):
        db.rollback()
        raise fail(status.HTTP_400_BAD_REQUEST, bad)
    previous = user.email if has_verified_email(user) else None
    address = row.target
    if address != user.email:
        user.email_from_google = False  # an address the user proved is theirs, not Google's
    user.email, user.email_verified = address, True
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise fail(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None
    audit.info("email verified user=%r email=%s ip=%s", user.username, mask_email(address), client_ip(request))
    if previous and previous != address:
        notify(request, background, user, "email_changed", to=previous, new_email=mask_email(address))
    return EmailVerifiedOut(email=address)


@router.delete("/me/email", response_model=MethodsStatus)
def remove_email(
    request: Request, background: BackgroundTasks, body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    try:
        user = session.user
        ensure_reauth(request, user, body.password if body else None)
        if has_verified_email(user) and usable_methods(user, without="email") == 0:
            raise fail(status.HTTP_409_CONFLICT, KEEP_ONE)
        previous = user.email if has_verified_email(user) else None
        user.email, user.email_verified, user.email_from_google = None, False, False
        drop_tokens(db, user.id, et.VERIFY)
        db.commit()
        audit.info("email removed user=%r ip=%s", user.username, client_ip(request))
        if previous:
            notify(request, background, user, "email_removed", to=previous)
        return methods_status(user)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("remove_email failed")
        raise


# --- sign in with an email -----------------------------------------------------------------------


def request_mail(
    request: Request, background: BackgroundTasks, db: Session, address: str, purpose: str
) -> OkOut:
    """Always the same work and the same answer; the mail goes out only for a VERIFIED matching account."""
    try:
        gate_request(request, purpose, address)
        user = verified_user(db, address)
        issued = et.issue(db, user, purpose, address, with_code=purpose == et.LOGIN)
        jitter()  # the same for both paths
        if user is not None:
            send_link_mail(request, background, purpose, address, issued.token, issued.code)
        audit.info("email %s requested ip=%s", purpose, client_ip(request))
        return OkOut()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("request_mail failed")
        raise


@router.post("/email/login/request", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def login_request(
    body: EmailBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    try:
        return request_mail(request, background, db, body.email, et.LOGIN)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("login_request failed")
        raise


@router.post("/email/login/verify", response_model=SessionOut | MfaRequired)
def login_with_code(
    body: EmailCodeBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    try:
        gate_submit(request)
        failure_key = code_failure_key(body.email)  # the submitted string only: existence is not revealed
        guard_code_attempts(request, failure_key)
        user = verified_user(db, body.email)
        row = et.find_for_user(db, user.id, et.LOGIN, body.email) if user else None
        if not et.check_code(db, row, body.code) or user is None or row is None or not et.consume(db, row.id):
            db.rollback()
            count_code_failure(request, failure_key)
            audit.warning("email code login failed ip=%s", client_ip(request))
            raise fail(status.HTTP_401_UNAUTHORIZED, BAD_CODE)
        db.commit()
        return login_result(request, response, db, user)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("login_with_code failed")
        raise


@router.post("/email/login/magic", response_model=SessionOut | MfaRequired)
def login_with_link(
    body: TokenBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    try:
        gate_submit(request)
        row = et.find_by_token(db, body.token, et.LOGIN)
        user = db.get(User, row.user_id) if row else None
        still_theirs = user is not None and has_verified_email(user) and row is not None and user.email == row.target
        if row is None or not still_theirs or not et.consume(db, row.id):
            db.rollback()
            audit.warning("email link login failed ip=%s", client_ip(request))
            raise fail(status.HTTP_401_UNAUTHORIZED, BAD_LINK)
        db.commit()
        return login_result(request, response, db, user)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("login_with_link failed")
        raise


# --- forgot / reset password ---------------------------------------------------------------------


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def forgot_password(
    body: EmailBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    try:
        return request_mail(request, background, db, body.email, et.RESET)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("forgot_password failed")
        raise


@router.post("/password/reset", response_model=OkOut)
def reset_password(
    body: ResetBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    """New password from a reset link. Does NOT sign in; every existing session and refresh token dies."""
    try:
        gate_submit(request)
        row = et.find_by_token(db, body.token, et.RESET)
        user = db.get(User, row.user_id) if row else None
        if row is None or user is None or not has_verified_email(user) or user.email != row.target:
            audit.warning("password reset failed ip=%s", client_ip(request))
            raise fail(status.HTTP_400_BAD_REQUEST, BAD_LINK)
        problem = password_problem(body.new_password)
        if problem:  # the token stays valid so the user can try again
            raise fail(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
        if not et.consume(db, row.id):
            db.rollback()
            raise fail(status.HTTP_400_BAD_REQUEST, BAD_LINK)
        user.password_hash = hash_password(body.new_password)
        bump_token_version(db, user)
        drop_tokens(db, user.id, et.RESET)
        db.commit()
        publish_token_version(user, settings_of(request))
        audit.info("password reset user=%r ip=%s", user.username, client_ip(request))
        notify(request, background, user, "password_reset")
        return OkOut()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("reset_password failed")
        raise
