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

from app import emailtokens as et
from app.audit import audit
from app.db import get_db
from app.deps import (
    AuthSession,
    biometrics_available,
    check_origin,
    client_ip,
    csrf_session,
    current_session,
    require_email,
    require_reauth,
    settings_of,
    too_many,
)
from app.mailer import mask_email
from app.methods import KEEP_ONE, has_verified_email, methods_status, usable_methods
from app.models import EmailToken, User
from app.notify import notify, send_link_mail
from app.passwords import hash_password, password_problem
from app.schemas import (
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
from app.sessions import start_login
from app.tokenversion import bump_token_version

BAD_LINK = "Invalid or expired link"
BAD_CODE = "Invalid or expired code"
EMAIL_TAKEN = "Email already in use"
MAX_JITTER_MS = 30

router = APIRouter(prefix="/auth", tags=["email"], dependencies=[Depends(require_email), Depends(check_origin)])


# --- shared helpers -------------------------------------------------------------------------------


def _fail(code: int, detail: str) -> HTTPException:
    return HTTPException(code, detail)


def _gate_submit(request: Request) -> None:
    """Link/code submissions: per address, every one counts (the 429 depends on counters only)."""
    throttle, ip = request.app.state.email_submit_throttle, client_ip(request)
    if throttle.is_blocked(ip):
        raise too_many()
    throttle.record(ip)


def _gate_request(request: Request, kind: str, address: str) -> None:
    """Mail requests, every one counts (known account or not): per IP, per (IP, normalised email) and per email.

    The pair counter stops one IP from spending the whole per-email budget, so a stranger cannot lock the owner out.
    """
    state, ip = request.app.state, client_ip(request)
    counters = (
        (state.email_login_ip_throttle, state.email_login_ip_addr_throttle, state.email_login_addr_throttle)
        if kind == et.LOGIN
        else (state.forgot_ip_throttle, state.forgot_ip_addr_throttle, state.forgot_addr_throttle)
    )
    keys = (ip, f"{ip}|{address}", address)
    if any(throttle.is_blocked(key) for throttle, key in zip(counters, keys)):
        raise too_many()
    for throttle, key in zip(counters, keys):
        throttle.record(key)


def _code_failure_key(address: str) -> str:
    return f"code|{address}"


def _guard_code_attempts(request: Request, key: str) -> None:
    """Failed code submissions per address across all rows (the 429 depends on the submitted string only)."""
    if request.app.state.email_code_fail_throttle.is_blocked(key):
        raise too_many()


def _count_code_failure(request: Request, key: str) -> None:
    request.app.state.email_code_fail_throttle.record(key)


def _jitter() -> None:
    """A small uniform random delay so the answer time does not tell a known address from an unknown one."""
    time.sleep(secrets.randbelow(MAX_JITTER_MS + 1) / 1000)


def _verified_owner_id(db: Session, address: str) -> int | None:
    return db.scalar(select(User.id).where(User.email == address, User.email_verified.is_(True)))


def _verified_user(db: Session, address: str) -> User | None:
    return db.scalar(select(User).where(User.email == address, User.email_verified.is_(True)))


def _drop_tokens(db: Session, user_id: int, purpose: str) -> None:
    db.execute(
        delete(EmailToken)
        .where(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
        .execution_options(synchronize_session=False)
    )


def _login_result(request: Request, response: Response, user: User) -> SessionOut | MfaRequired:
    """Email is a primary factor: same hand-off as password and Google (the opt-in second factor applies)."""
    result = start_login(response, user, settings_of(request), biometrics_available(request))
    audit.info("login %s (email) user=%r ip=%s", "mfa-pending" if isinstance(result, MfaRequired) else "ok",
               user.username, client_ip(request))  # fmt: skip
    return result


# --- add / verify / remove an address -------------------------------------------------------------


@router.post("/me/email", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def set_email(
    body: SetEmailBody, request: Request, background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> OkOut:  # fmt: skip
    """Start (or resend) verification of an address. `users.email` changes only when it is verified."""
    user, state = session.user, request.app.state
    user_throttle, target_throttle = state.email_change_throttle, state.email_change_target_throttle
    if user_throttle.is_blocked(str(user.id)) or target_throttle.is_blocked(body.email):
        raise too_many()
    require_reauth(request, user, body.password)
    user_throttle.record(str(user.id))
    target_throttle.record(body.email)  # per target address: this route cannot be used to mail-bomb a stranger
    owner = _verified_owner_id(db, body.email)
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


@router.post("/email/verify", response_model=EmailVerifiedOut)
def verify_email(
    body: EmailVerifyBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> EmailVerifiedOut:
    """`{token}` (the link, public) or `{code}` (typed in the account: needs the session)."""
    _gate_submit(request)
    failure_key = None
    if body.token:
        row, bad = et.find_by_token(db, body.token, et.VERIFY), BAD_LINK
        accepted = row is not None
    else:
        user = current_session(request, db).user
        failure_key = _code_failure_key(f"user:{user.id}")  # the address is not submitted here: key by the account
        _guard_code_attempts(request, failure_key)
        row, bad = et.find_for_user(db, user.id, et.VERIFY), BAD_CODE
        accepted = et.check_code(db, row, body.code or "")
    if not accepted or row is None:
        if failure_key:
            _count_code_failure(request, failure_key)
        audit.warning("email verification failed ip=%s", client_ip(request))
        raise _fail(status.HTTP_400_BAD_REQUEST, bad)
    owner = _verified_owner_id(db, row.email)
    if owner is not None and owner != row.user_id:
        raise _fail(status.HTTP_409_CONFLICT, EMAIL_TAKEN)  # verified elsewhere in the meantime
    user = db.get(User, row.user_id)
    if user is None or not et.consume(db, row.id):
        db.rollback()
        raise _fail(status.HTTP_400_BAD_REQUEST, bad)
    previous = user.email if has_verified_email(user) else None
    address = row.email
    if address != user.email:
        user.email_from_google = False  # an address the user proved is theirs, not Google's
    user.email, user.email_verified = address, True
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _fail(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None
    audit.info("email verified user=%r email=%s ip=%s", user.username, mask_email(address), client_ip(request))
    if previous and previous != address:
        notify(request, background, user, "email_changed", to=previous, new_email=mask_email(address))
    return EmailVerifiedOut(email=address)


@router.delete("/me/email", response_model=MethodsStatus)
def remove_email(
    request: Request, background: BackgroundTasks, body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    user = session.user
    require_reauth(request, user, body.password if body else None)
    if has_verified_email(user) and usable_methods(user, without="email") == 0:
        raise _fail(status.HTTP_409_CONFLICT, KEEP_ONE)
    previous = user.email if has_verified_email(user) else None
    user.email, user.email_verified, user.email_from_google = None, False, False
    _drop_tokens(db, user.id, et.VERIFY)
    db.commit()
    audit.info("email removed user=%r ip=%s", user.username, client_ip(request))
    if previous:
        notify(request, background, user, "email_removed", to=previous)
    return methods_status(user)


# --- sign in with an email -----------------------------------------------------------------------


def _request_mail(
    request: Request, background: BackgroundTasks, db: Session, address: str, purpose: str
) -> OkOut:
    """Always the same work and the same answer; the mail goes out only for a VERIFIED matching account."""
    _gate_request(request, purpose, address)
    user = _verified_user(db, address)
    issued = et.issue(db, user, purpose, address, with_code=purpose == et.LOGIN)
    _jitter()  # the same for both paths
    if user is not None:
        send_link_mail(request, background, purpose, address, issued.token, issued.code)
    audit.info("email %s requested ip=%s", purpose, client_ip(request))
    return OkOut()


@router.post("/email/login/request", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def login_request(
    body: EmailBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    return _request_mail(request, background, db, body.email, et.LOGIN)


@router.post("/email/login/verify", response_model=SessionOut | MfaRequired)
def login_with_code(
    body: EmailCodeBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    _gate_submit(request)
    failure_key = _code_failure_key(body.email)  # the submitted string only: existence is not revealed
    _guard_code_attempts(request, failure_key)
    user = _verified_user(db, body.email)
    row = et.find_for_user(db, user.id, et.LOGIN, body.email) if user else None
    if not et.check_code(db, row, body.code) or user is None or row is None or not et.consume(db, row.id):
        db.rollback()
        _count_code_failure(request, failure_key)
        audit.warning("email code login failed ip=%s", client_ip(request))
        raise _fail(status.HTTP_401_UNAUTHORIZED, BAD_CODE)
    db.commit()
    return _login_result(request, response, user)


@router.post("/email/login/magic", response_model=SessionOut | MfaRequired)
def login_with_link(
    body: TokenBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    _gate_submit(request)
    row = et.find_by_token(db, body.token, et.LOGIN)
    user = db.get(User, row.user_id) if row else None
    still_theirs = user is not None and has_verified_email(user) and row is not None and user.email == row.email
    if row is None or not still_theirs or not et.consume(db, row.id):
        db.rollback()
        audit.warning("email link login failed ip=%s", client_ip(request))
        raise _fail(status.HTTP_401_UNAUTHORIZED, BAD_LINK)
    db.commit()
    return _login_result(request, response, user)


# --- forgot / reset password ---------------------------------------------------------------------


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def forgot_password(
    body: EmailBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    return _request_mail(request, background, db, body.email, et.RESET)


@router.post("/password/reset", response_model=OkOut)
def reset_password(
    body: ResetBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    """New password from a reset link. Does NOT sign in; every existing session and refresh token dies."""
    _gate_submit(request)
    row = et.find_by_token(db, body.token, et.RESET)
    user = db.get(User, row.user_id) if row else None
    if row is None or user is None or not has_verified_email(user) or user.email != row.email:
        audit.warning("password reset failed ip=%s", client_ip(request))
        raise _fail(status.HTTP_400_BAD_REQUEST, BAD_LINK)
    problem = password_problem(body.new_password, user.username)
    if problem:  # the token stays valid so the user can try again
        raise _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    if not et.consume(db, row.id):
        db.rollback()
        raise _fail(status.HTTP_400_BAD_REQUEST, BAD_LINK)
    user.password_hash = hash_password(body.new_password)
    bump_token_version(db, user)
    _drop_tokens(db, user.id, et.RESET)
    db.commit()
    audit.info("password reset user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "password_reset")
    return OkOut()
