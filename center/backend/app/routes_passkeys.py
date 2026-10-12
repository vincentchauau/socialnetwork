"""Passkey (WebAuthn) sign-in: sign in without a username, link/manage passkeys, sign-up options.

Every sign-in failure is the same 401 and never says why. Audit lines carry the outcome and address only.
Re-auth follows the other method routes: the password is asked (when the account has one) when the
registration ceremony starts, since the finishing request is bound to that account by the challenge token.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import passkeys as pk
from app.audit import audit
from app.db import get_db
from app.deps import AuthSession, check_origin, client_ip, csrf_session, current_session, require_reauth, settings_of, too_many
from app.methods import KEEP_ONE, passkey_items, usable_methods
from app.models import Passkey, User, utcnow
from app.schemas import (
    DeleteAccountBody,
    PasskeyAddBody,
    PasskeyList,
    PasskeyLoginBody,
    PasskeyOptionsBody,
    PasskeyOptionsOut,
    PasskeyRenameBody,
    PasskeySignupOptionsBody,
    SessionOut,
)
from app.sessions import issue_session

LOGIN_FAILED = "Passkey sign-in failed"
REGISTRATION_FAILED = "Passkey registration failed"
DUPLICATE = "This passkey is already registered"
NOT_FOUND = "Passkey not found"
SIGNUP_DISPLAY_NAME = "Passkey"

router = APIRouter(prefix="/auth", tags=["passkeys"], dependencies=[Depends(check_origin)])


def _store(request: Request) -> pk.ChallengeStore:
    return request.app.state.passkey_challenges


def _options_gate(request: Request) -> None:
    """Per-address cap on option requests (every call counts)."""
    throttle, ip = request.app.state.passkey_options_throttle, client_ip(request)
    if throttle.is_blocked(ip):
        audit.warning("passkey options locked ip=%s", ip)
        raise too_many()
    throttle.record(ip)


def _options_out(options: dict, token: str) -> PasskeyOptionsOut:
    return PasskeyOptionsOut(options=options, challenge_token=token)


# --- sign in --------------------------------------------------------------------------------------


@router.post("/passkey/options", response_model=PasskeyOptionsOut)
def login_options(request: Request) -> PasskeyOptionsOut:
    _options_gate(request)
    options, challenge = pk.request_options(settings_of(request))
    return _options_out(options, pk.mint_challenge(pk.LOGIN, challenge))


def _verified_login(request: Request, db: Session, body: PasskeyLoginBody) -> Passkey:
    settings = settings_of(request)
    challenge = pk.read_challenge(body.challenge_token, pk.LOGIN, _store(request))
    passkey = db.scalar(select(Passkey).where(Passkey.credential_id == pk.credential_id_of(body.credential)))
    if passkey is None:
        raise pk.PasskeyError("unknown credential")
    assertion = pk.verify_assertion(settings, body.credential, challenge, passkey)
    if pk.sign_count_regressed(passkey.sign_count, assertion.new_sign_count):
        audit.warning("passkey possible cloned authenticator ip=%s", client_ip(request))
        raise pk.PasskeyError("sign count regressed")
    passkey.sign_count = assertion.new_sign_count
    passkey.backed_up = assertion.backed_up
    passkey.last_used_at = utcnow()
    return passkey


@router.post("/passkey/login", response_model=SessionOut)
def passkey_login(
    body: PasskeyLoginBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut:
    ip, throttle = client_ip(request), request.app.state.passkey_login_throttle
    if throttle.is_blocked(ip):
        audit.warning("passkey login locked ip=%s", ip)
        raise too_many()
    try:
        passkey = _verified_login(request, db, body)
    except pk.PasskeyError:
        db.rollback()
        throttle.record(ip)
        audit.warning("passkey login failed ip=%s", ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED) from None
    db.commit()
    throttle.reset(ip)
    audit.info("login ok (passkey) user=%r ip=%s", passkey.user.username, ip)
    return issue_session(response, passkey.user, settings_of(request))


# --- sign up --------------------------------------------------------------------------------------


@router.post("/register/passkey/options", response_model=PasskeyOptionsOut)
def signup_options(body: PasskeySignupOptionsBody, request: Request) -> PasskeyOptionsOut:
    _options_gate(request)
    handle = pk.new_user_handle()
    name = (body.username or "").strip() or None
    options, challenge = pk.creation_options(
        settings_of(request), user_name=name or SIGNUP_DISPLAY_NAME, display_name=name or SIGNUP_DISPLAY_NAME,
        user_handle=handle,
    )  # fmt: skip
    return _options_out(options, pk.mint_challenge(pk.SIGNUP, challenge, user_handle=handle, username=name))


def verified_signup_passkey(request: Request, db: Session, credential_json: str, token: str) -> Passkey:
    """The Passkey row for an all-or-nothing registration (not added to the session yet).

    HTTP 400 for any verification problem, 409 for a credential that is already registered.
    """
    try:
        credential = json.loads(credential_json)
        challenge = pk.read_challenge(token, pk.SIGNUP, _store(request))
        columns = pk.verify_registration(settings_of(request), credential, challenge)
    except (ValueError, pk.PasskeyError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, REGISTRATION_FAILED) from None
    if db.scalar(select(Passkey.id).where(Passkey.credential_id == columns["credential_id"])) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE)
    return Passkey(name=pk.DEFAULT_PASSKEY_NAME, **columns)


# --- link and manage ------------------------------------------------------------------------------


def _listing(user: User) -> PasskeyList:
    return PasskeyList(passkeys=passkey_items(user))


@router.post("/me/passkeys/options", response_model=PasskeyOptionsOut)
def link_options(
    request: Request, body: PasskeyOptionsBody | None = None, session: AuthSession = Depends(csrf_session)
) -> PasskeyOptionsOut:
    user = session.user
    _options_gate(request)
    require_reauth(request, user, body.password if body else None)
    handle = pk.user_handle_of(user) or pk.new_user_handle()
    options, challenge = pk.creation_options(
        settings_of(request), user_name=user.username, display_name=user.username, user_handle=handle,
        existing=list(user.passkeys),
    )  # fmt: skip
    token = pk.mint_challenge(pk.LINK, challenge, user_id=user.id, user_handle=handle)
    return _options_out(options, token)


@router.post("/me/passkeys", response_model=PasskeyList)
def add_passkey(
    body: PasskeyAddBody, request: Request, session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> PasskeyList:  # fmt: skip
    user = session.user
    try:
        challenge = pk.read_challenge(body.challenge_token, pk.LINK, _store(request))
        if challenge.user_id != user.id:
            raise pk.PasskeyError("challenge belongs to another account")
        columns = pk.verify_registration(settings_of(request), body.credential, challenge)
    except pk.PasskeyError:
        audit.warning("passkey registration failed user=%r ip=%s", user.username, client_ip(request))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, REGISTRATION_FAILED) from None
    if db.scalar(select(Passkey.id).where(Passkey.credential_id == columns["credential_id"])) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE)
    columns["user_handle"] = pk.user_handle_of(user) or columns["user_handle"]  # one handle per account
    user.passkeys.append(Passkey(name=(body.name or "").strip() or pk.DEFAULT_PASSKEY_NAME, **columns))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE) from None
    audit.info("passkey added user=%r ip=%s", user.username, client_ip(request))
    return _listing(user)


@router.get("/me/passkeys", response_model=PasskeyList)
def list_passkeys(session: AuthSession = Depends(current_session)) -> PasskeyList:
    return _listing(session.user)


def _own(user: User, passkey_id: int) -> Passkey:
    for passkey in user.passkeys:
        if passkey.id == passkey_id:
            return passkey
    raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


@router.patch("/me/passkeys/{passkey_id}", response_model=PasskeyList)
def rename_passkey(
    passkey_id: int, body: PasskeyRenameBody, session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> PasskeyList:  # fmt: skip
    passkey = _own(session.user, passkey_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name: Enter a name")
    passkey.name = name
    db.commit()
    return _listing(session.user)


@router.delete("/me/passkeys/{passkey_id}", response_model=PasskeyList)
def delete_passkey(
    passkey_id: int, request: Request, body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> PasskeyList:  # fmt: skip
    user = session.user
    passkey = _own(user, passkey_id)
    require_reauth(request, user, body.password if body else None)
    if len(user.passkeys) == 1 and usable_methods(user, without="passkey") == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, KEEP_ONE)
    user.passkeys.remove(passkey)
    db.commit()
    audit.info("passkey removed user=%r ip=%s", user.username, client_ip(request))
    return _listing(user)
