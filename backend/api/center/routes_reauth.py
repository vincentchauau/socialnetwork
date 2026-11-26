"""Step-up re-authentication: obtain the short-lived `sn_fresh` cookie (see app.reauth).

Each route proves the account owner is present with something other than the password: a passkey of the
CURRENT user, the Google account linked to it, or a 6-digit code mailed to its VERIFIED email. Every failure is
the same 401 and counts against a per-user throttle; success sets the cookie and returns `{fresh_until}`.
"""

import hashlib
import secrets
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.center import emailtokens as et
from api.center import passkeys as pk
from api.center import routes_email as email_routes
from api.center.audit import audit
from api.center.db import get_db
from api.center.deps import AuthSession, check_origin, client_ip, csrf_session, current_session, ensure_email, settings_of, too_many
from api.center.methods import has_verified_email
from api.center.models import Passkey, User, utcnow
from api.center.notify import send_code_mail
from api.center.reauth import REAUTH_FAILED, available_methods, set_fresh
from api.center.routes_auth import verify_google_or_throttle
from api.center.routes_passkeys import options_gate, options_out, store_routes_passkeys
from api.center.schemas import FreshOut, GoogleBody, OkOut, PasskeyLoginBody, PasskeyOptionsOut, ReauthCodeBody, ReauthMethodsOut

GOOGLE_PROOF_TTL_SECONDS = 3600.0  # Google ID tokens live an hour

router = APIRouter(prefix="/auth/reauth", tags=["reauth"], dependencies=[Depends(check_origin)])


def throttle_key(request: Request, user: User) -> str:
    return f"{user.id}|{client_ip(request)}"


def guard(request: Request, user: User) -> None:
    if request.app.state.fresh_throttle.is_blocked(throttle_key(request, user)):
        audit.warning("reauth locked user=%r ip=%s", user.username, client_ip(request))
        raise too_many()


def fail(request: Request, user: User, how: str) -> HTTPException:
    request.app.state.fresh_throttle.record(throttle_key(request, user))
    audit.warning("reauth %s failed user=%r ip=%s", how, user.username, client_ip(request))
    return HTTPException(status.HTTP_401_UNAUTHORIZED, REAUTH_FAILED)


def granted(request: Request, response: Response, user: User, how: str) -> FreshOut:
    request.app.state.fresh_throttle.reset(throttle_key(request, user))
    audit.info("reauth ok (%s) user=%r ip=%s", how, user.username, client_ip(request))
    return set_fresh(response, request, user, settings_of(request))


@router.get("/methods", response_model=ReauthMethodsOut)
def methods(request: Request, session: AuthSession = Depends(current_session)) -> ReauthMethodsOut:
    return ReauthMethodsOut(methods=available_methods(request, session.user))


# --- passkey ---------------------------------------------------------------------------------------


@router.post("/passkey/options", response_model=PasskeyOptionsOut)
def passkey_options(request: Request, session: AuthSession = Depends(csrf_session)) -> PasskeyOptionsOut:
    options_gate(request)
    options, challenge = pk.request_options(settings_of(request))
    return options_out(options, pk.mint_challenge(pk.REAUTH, challenge, user_id=session.user.id))


def verified_own_passkey(request: Request, db: Session, user: User, body: PasskeyLoginBody) -> Passkey:
    challenge = pk.read_challenge(body.challenge_token, pk.REAUTH, store_routes_passkeys(request))  # single use
    if challenge.user_id != user.id:
        raise pk.PasskeyError("challenge belongs to another account")
    passkey = db.scalar(select(Passkey).where(Passkey.credential_id == pk.credential_id_of(body.credential)))
    if passkey is None or passkey.user_id != user.id:
        raise pk.PasskeyError("not a passkey of this account")
    assertion = pk.verify_assertion(settings_of(request), body.credential, challenge, passkey)  # UV required
    if pk.sign_count_regressed(passkey.sign_count, assertion.new_sign_count):
        audit.warning("passkey possible cloned authenticator ip=%s", client_ip(request))
        raise pk.PasskeyError("sign count regressed")
    passkey.sign_count = assertion.new_sign_count
    passkey.backed_up = assertion.backed_up
    passkey.last_used_at = utcnow()
    return passkey


@router.post("/passkey/verify", response_model=FreshOut)
def passkey_verify(
    body: PasskeyLoginBody, request: Request, response: Response,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> FreshOut:  # fmt: skip
    user = session.user
    guard(request, user)
    try:
        verified_own_passkey(request, db, user, body)
    except pk.PasskeyError:
        db.rollback()
        raise fail(request, user, "passkey") from None
    db.commit()
    return granted(request, response, user, "passkey")


# --- Google ----------------------------------------------------------------------------------------


@router.post("/google", response_model=FreshOut)
def google(
    body: GoogleBody, request: Request, response: Response, session: AuthSession = Depends(csrf_session)
) -> FreshOut:
    user = session.user
    guard(request, user)
    try:
        identity = verify_google_or_throttle(request, body.id_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            raise fail(request, user, "google") from None
        raise
    if user.google_sub is None or not secrets.compare_digest(identity.sub, user.google_sub):
        raise fail(request, user, "google")
    ttl = max(1.0, identity.exp - time.time()) if identity.exp else GOOGLE_PROOF_TTL_SECONDS
    digest = hashlib.sha256(body.id_token.encode()).hexdigest()
    if not request.app.state.kv.set_if_absent(f"google-reauth:{digest}", ttl):  # one ID token, one proof
        raise fail(request, user, "google")
    return granted(request, response, user, "google")


# --- mailed code -----------------------------------------------------------------------------------


@router.post(
    "/email/request", status_code=status.HTTP_202_ACCEPTED, response_model=OkOut, dependencies=[Depends(ensure_email)]
)
def email_request(
    request: Request, background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> OkOut:  # fmt: skip
    """Mail a code to the account's VERIFIED address (never to one the caller supplies). Same 202 either way."""
    user = session.user
    address = user.email if has_verified_email(user) else None
    email_routes.gate_request(request, et.REAUTH, address or f"user:{user.id}")
    issued = et.issue(db, user if address else None, et.REAUTH, address or "", with_code=True)
    email_routes.jitter()
    if address and issued.code:
        send_code_mail(request, background, et.REAUTH, address, issued.code)
    audit.info("reauth mail requested user=%r ip=%s", user.username, client_ip(request))
    return OkOut()


@router.post("/email/verify", response_model=FreshOut, dependencies=[Depends(ensure_email)])
def email_verify(
    body: ReauthCodeBody, request: Request, response: Response,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> FreshOut:  # fmt: skip
    user = session.user
    guard(request, user)
    email_routes.gate_submit(request)
    failure_key = email_routes.code_failure_key(f"reauth:{user.id}")
    email_routes.guard_code_attempts(request, failure_key)
    address = user.email if has_verified_email(user) else None
    row = et.find_for_user(db, user.id, et.REAUTH, address) if address else None
    if not et.check_code(db, row, body.code) or row is None or not et.consume(db, row.id):
        db.rollback()
        email_routes.count_code_failure(request, failure_key)
        raise fail(request, user, "email")
    db.commit()
    return granted(request, response, user, "email")
