"""Phone: verify a number by SMS code, sign in with an SMS code, remove the number.

Same rules as the email routes: request routes answer one identical 202 whether or not the number has an
account, every code failure is one generic 4xx, and SMS cost is bounded by per-IP, per-(IP, number),
per-number and global daily budgets (only real sends count against the daily cap).
"""

import secrets
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.center import phones as ph
from api.center.audit import audit
from api.center.db import get_db
from api.center.deps import (
    AuthSession, biometrics_available, check_origin, client_ip, csrf_session, ensure_reauth, settings_of, too_many,
)
from api.center.methods import KEEP_ONE, methods_status, usable_methods
from api.center.models import User
from api.center.notify import notify
from api.center.phonenum import log_phone, mask_phone, normalize_phone
from api.center.schemas import DeleteAccountBody, MethodsStatus, MfaRequired, OkOut, SessionOut
from api.center.sessions import start_login

BAD_CODE = "Invalid or expired code"
BAD_PHONE = "Invalid phone number"
PHONE_TAKEN = "Phone number already in use"
MAX_JITTER_MS = 30


def ensure_phone(request: Request) -> None:
    if not settings_of(request).phone_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Phone sign-in is not available")


router = APIRouter(prefix="/auth", tags=["phone"], dependencies=[Depends(ensure_phone), Depends(check_origin)])


class SetPhoneBody(BaseModel):
    phone: str = Field(max_length=32)
    password: str | None = Field(default=None, max_length=1024)


class PhoneBody(BaseModel):
    phone: str = Field(max_length=32)


class PhoneCodeBody(PhoneBody):
    code: str = Field(max_length=32)


class VerifyCodeBody(BaseModel):
    code: str = Field(max_length=32)


def valid_phone(request: Request, raw: str) -> str:
    phone = normalize_phone(raw, settings_of(request).sms_allowed_prefixes)
    if phone is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, BAD_PHONE)
    return phone


def jitter() -> None:
    time.sleep(secrets.randbelow(MAX_JITTER_MS + 1) / 1000)


def verified_user(db: Session, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == phone, User.phone_verified.is_(True)))


def spend_daily_routes_phone(request: Request, purpose: str) -> None:
    """Count one REAL send against the flow's share of the daily cap (429 when it is spent)."""
    if not ph.spend_daily(request, purpose):
        raise too_many()


def gate_request(request: Request, phone: str, purpose: str) -> None:
    state, ip = request.app.state, client_ip(request)
    if state.sms_daily_throttle[purpose].is_blocked(ph.DAILY_KEY):
        raise too_many()  # the same for every number: the cap says nothing about an account
    counters = (
        (state.sms_ip_throttle, ip), (state.sms_ip_phone_throttle, f"{ip}|{phone}"), (state.sms_phone_throttle, phone),
        (state.sms_phone_day_throttle, phone),
    )
    if any(throttle.is_blocked(key) for throttle, key in counters):
        raise too_many()
    for throttle, key in counters:
        throttle.record(key)


# --- add / verify / remove a number ---------------------------------------------------------------


@router.post("/me/phone", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def set_phone(
    body: SetPhoneBody, request: Request, background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> OkOut:  # fmt: skip
    """Start (or resend) verification of a number. `users.phone` changes only when it is verified."""
    user, state = session.user, request.app.state
    phone = valid_phone(request, body.phone)
    if state.sms_user_throttle.is_blocked(str(user.id)):
        raise too_many()
    ensure_reauth(request, user, body.password)
    if state.sms_user_day_throttle.is_blocked(str(user.id)):
        raise too_many()
    gate_request(request, phone, ph.VERIFY)
    state.sms_user_throttle.record(str(user.id))
    state.sms_user_day_throttle.record(str(user.id))
    owner = db.scalar(select(User.id).where(User.phone == phone, User.phone_verified.is_(True)))
    if owner is not None and owner != user.id:
        ph.issue(db, None, ph.VERIFY, phone)  # taken: answer like a success, send nothing
        audit.info("phone verification skipped (taken) user=%r ip=%s", user.username, client_ip(request))
        return OkOut()
    code = ph.issue(db, user, ph.VERIFY, phone)
    spend_daily_routes_phone(request, ph.VERIFY)
    ph.queue_sms(request, background, ph.VERIFY, phone, code)
    audit.info("phone verification requested user=%r phone=%s ip=%s", user.username, log_phone(phone),
               client_ip(request))  # fmt: skip
    return OkOut()


@router.post("/me/phone/verify", response_model=MethodsStatus)
def verify_phone(
    body: VerifyCodeBody, request: Request, background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    state, user = request.app.state, session.user
    if not state.sms_submit_throttle.check_and_record(client_ip(request)):
        raise too_many()
    if not state.sms_fail_throttle.check_and_record(f"user:{user.id}"):
        raise too_many()
    row = ph.find_for_user(db, user.id, ph.VERIFY)
    if not ph.check_code(db, row, body.code) or row is None:
        audit.warning("phone verification failed user=%r ip=%s", user.username, client_ip(request))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)
    owner = db.scalar(select(User.id).where(User.phone == row.target, User.phone_verified.is_(True)))
    if owner is not None and owner != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_TAKEN)
    if not ph.consume(db, row.id):
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)
    user.phone, user.phone_verified = row.target, True
    ph.drop_codes(db, user.id, ph.VERIFY)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, PHONE_TAKEN) from None
    audit.info("phone verified user=%r phone=%s ip=%s", user.username, log_phone(user.phone), client_ip(request))
    notify(request, background, user, "phone_added", phone=mask_phone(user.phone))
    return methods_status(user)


@router.delete("/me/phone", response_model=MethodsStatus)
def remove_phone(
    request: Request, background: BackgroundTasks, body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> MethodsStatus:  # fmt: skip
    user = session.user
    ensure_reauth(request, user, body.password if body else None)
    had = bool(user.phone and user.phone_verified)
    if had and usable_methods(user, without="phone") == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, KEEP_ONE)
    old = mask_phone(user.phone) if had else None
    user.phone, user.phone_verified = None, False
    ph.drop_codes(db, user.id, ph.VERIFY)
    ph.drop_codes(db, user.id, ph.LOGIN)
    db.commit()
    audit.info("phone removed user=%r ip=%s", user.username, client_ip(request))
    if had:
        notify(request, background, user, "phone_removed", phone=old)
    return methods_status(user)


# --- sign in with an SMS code ---------------------------------------------------------------------


@router.post("/phone/login/request", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut)
def login_request(
    body: PhoneBody, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> OkOut:
    """Always the same work and answer; an SMS goes out only for a VERIFIED number."""
    phone = valid_phone(request, body.phone)
    gate_request(request, phone, ph.LOGIN)
    user = verified_user(db, phone)
    code = ph.issue(db, user, ph.LOGIN, phone)
    jitter()
    if user is not None:
        spend_daily_routes_phone(request, ph.LOGIN)
        ph.queue_sms(request, background, ph.LOGIN, phone, code)
    audit.info("phone login requested ip=%s", client_ip(request))
    return OkOut()


@router.post("/phone/login/verify", response_model=SessionOut | MfaRequired)
def login_verify(
    body: PhoneCodeBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    state = request.app.state
    if not state.sms_submit_throttle.check_and_record(client_ip(request)):
        raise too_many()
    phone = normalize_phone(body.phone, settings_of(request).sms_allowed_prefixes) or "invalid"
    pair = f"{client_ip(request)}|{phone}"  # per (IP, number): a stranger's guesses cannot lock the owner out
    if not state.sms_fail_throttle.check_and_record(pair) or not state.sms_fail_phone_throttle.check_and_record(phone):
        raise too_many()
    user = verified_user(db, phone)
    row = ph.find_for_user(db, user.id, ph.LOGIN, phone) if user else None
    if not ph.check_code(db, row, body.code) or user is None or row is None or not ph.consume(db, row.id):
        db.rollback()
        audit.warning("phone code login failed ip=%s", client_ip(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CODE)
    db.commit()
    state.sms_fail_throttle.reset(pair)
    result = start_login(
        response, user, settings_of(request), biometrics_available(request), request=request, db=db, method="phone"
    )
    audit.info("login %s (phone) user=%r ip=%s", "mfa-pending" if isinstance(result, MfaRequired) else "ok",
               user.username, client_ip(request))  # fmt: skip
    return result
