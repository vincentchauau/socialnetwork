"""Register, login, refresh, logout, me, Google sign-in."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import audit
from app.db import get_db
from app.deps import (
    AuthSession,
    biometrics_available,
    check_origin,
    client_ip,
    csrf_session,
    current_session,
    settings_of,
    too_many,
)
from app.google_auth import GoogleAuthError, GoogleIdentity
from app.handles import unique_handle
from app.methods import methods_status
from app.models import User
from app.passwords import NO_PASSWORD, hash_password, needs_rehash, password_problem, verify_password
from app.schemas import AuthConfig, Credentials, GoogleBody, LoginBody, MeOut, MfaRequired, SessionOut
from app.sessions import REFRESH_COOKIE, clear_session_cookies, issue_session, start_login
from app.tokens import csrf_token, decode_typed
from sn_shared.security import AuthError

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(check_origin)])

BAD_LOGIN = "Invalid username or password"
GOOGLE_NOT_CONFIGURED = "Google sign-in is not configured"
MAX_HANDLE_ATTEMPTS = 5

# Verified against when the username is unknown, so response time does not
# reveal whether an account exists.
_DUMMY_HASH = hash_password("dummy-password")


def me_out(user: User, token: str) -> MeOut:
    return MeOut(
        id=user.id,
        username=user.username,
        role=user.role,
        email=user.email,
        csrf_token=csrf_token(token),
        **methods_status(user).model_dump(),
    )


@router.get("/config", response_model=AuthConfig)
def auth_config(request: Request) -> AuthConfig:
    s = settings_of(request)
    return AuthConfig(google_client_id=s.google_client_id or None, biometrics_enabled=s.biometrics_enabled)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut:
    throttle, ip = request.app.state.register_throttle, client_ip(request)
    if throttle.is_blocked(ip):
        raise too_many()
    throttle.record(ip)
    problem = password_problem(body.password, body.username)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken") from None
    audit.info("register user=%r ip=%s", user.username, ip)
    return issue_session(response, user, settings_of(request))


def _login_throttles(request: Request, ip: str, name: str) -> tuple[list, list[str]]:
    """(throttles, keys) in matching order: per ip+user, per ip, per account (all IPs)."""
    state = request.app.state
    return (
        [state.login_throttle, state.login_ip_throttle, state.login_account_throttle],
        [f"{ip}|{name}", ip, name],
    )


@router.post("/login", response_model=SessionOut | MfaRequired)
def login(
    body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    ip, name = client_ip(request), body.username
    throttles, keys = _login_throttles(request, ip, name)
    if any(t.is_blocked(k) for t, k in zip(throttles, keys)):
        audit.warning("login locked user=%r ip=%s", name, ip)
        raise too_many()
    user = db.scalar(select(User).where(User.username == name))
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok:
        for throttle, key in zip(throttles, keys):
            throttle.record(key)
        audit.warning("login failed user=%r ip=%s", name, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_LOGIN)
    throttles[0].reset(keys[0])
    throttles[2].reset(keys[2])
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password[:128])  # bcrypt -> scrypt
        db.commit()
    result = start_login(response, user, settings_of(request), biometrics_available(request))
    audit.info("login %s user=%r ip=%s", "mfa-pending" if isinstance(result, MfaRequired) else "ok", name, ip)
    return result


def _reject_refresh(settings, reason: str, ip: str) -> JSONResponse:
    audit.warning("refresh rejected ip=%s reason=%s", ip, reason)
    rejected = JSONResponse({"detail": "Invalid refresh token"}, status_code=status.HTTP_401_UNAUTHORIZED)
    clear_session_cookies(rejected, settings)
    return rejected


@router.post("/refresh", response_model=SessionOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    settings, ip = settings_of(request), client_ip(request)
    throttle = request.app.state.refresh_throttle
    if throttle.is_blocked(ip):
        raise too_many()
    throttle.record(ip)
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return _reject_refresh(settings, "missing", ip)
    try:
        user_id, ver = decode_typed(token, "refresh")
    except AuthError:
        return _reject_refresh(settings, "invalid", ip)
    user = db.get(User, user_id)
    if user is None or user.token_version != ver:
        return _reject_refresh(settings, "revoked", ip)
    audit.info("refresh ok user=%r ip=%s", user.username, ip)
    return issue_session(response, user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> None:
    session.user.token_version += 1  # revokes every refresh token and center-side session
    db.commit()
    clear_session_cookies(response, settings_of(request))
    audit.info("logout user=%r ip=%s", session.user.username, client_ip(request))


@router.get("/me", response_model=MeOut)
def me(session: AuthSession = Depends(current_session)) -> MeOut:
    return me_out(session.user, session.token)


def _verify_google(request: Request, id_token: str) -> GoogleIdentity:
    verifier = request.app.state.google_verifier
    if verifier is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, GOOGLE_NOT_CONFIGURED)
    try:
        return verifier(id_token)
    except GoogleAuthError as exc:
        audit.warning("google token rejected ip=%s reason=%s", client_ip(request), exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Google token") from None


def verify_google_or_throttle(request: Request, id_token: str) -> GoogleIdentity:
    """Verify an ID token; failures count against the per-IP login throttle."""
    throttle, ip = request.app.state.login_ip_throttle, client_ip(request)
    if throttle.is_blocked(ip):
        raise too_many()
    try:
        return _verify_google(request, id_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            throttle.record(ip)
        raise


def _create_google_user(db: Session, identity: GoogleIdentity) -> User:
    for _ in range(MAX_HANDLE_ATTEMPTS):
        handle = unique_handle(
            identity.email, lambda h: db.scalar(select(User.id).where(User.username == h)) is not None
        )
        email_taken = db.scalar(select(User.id).where(User.email == identity.email)) is not None
        user = User(
            username=handle,
            password_hash=NO_PASSWORD,
            email=None if email_taken else identity.email,
            google_sub=identity.sub,
        )
        db.add(user)
        try:
            db.commit()
            return user
        except IntegrityError:  # lost a race on the handle/email/sub: look again
            db.rollback()
            existing = db.scalar(select(User).where(User.google_sub == identity.sub))
            if existing is not None:
                return existing
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not create the account, try again")


@router.post("/google", response_model=SessionOut | MfaRequired)
def google_login(
    body: GoogleBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionOut | MfaRequired:
    ip = client_ip(request)
    identity = verify_google_or_throttle(request, body.id_token)
    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    created = user is None
    if user is None:
        throttle = request.app.state.register_throttle
        if throttle.is_blocked(ip):
            raise too_many()
        throttle.record(ip)
        user = _create_google_user(db, identity)
    audit.info("google %s user=%r ip=%s", "register" if created else "login", user.username, ip)
    return start_login(response, user, settings_of(request), biometrics_available(request))
