"""Shared request dependencies: settings, origin check, current user, CSRF, throttled re-auth."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from api.center import usersessions
from api.center.audit import audit
from api.center.config import Settings
from api.center.db import get_db
from api.center.models import User
from api.center.passwords import verify_password
from api.center.reauth import ReauthRequired, available_methods, has_fresh_proof
from api.center.tokens import csrf_valid
from sn_shared import COOKIE_NAME
from sn_shared.security import AuthError, decode_token

UNSAFE_METHODS = ("POST", "PUT", "DELETE", "PATCH")
BAD_REAUTH = "Incorrect password"


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def biometrics_available(request: Request) -> bool:
    return settings_of(request).biometrics_enabled and request.app.state.biometrics is not None


def client_ip(request: Request) -> str:
    # Behind the gateway uvicorn runs with --proxy-headers, so this is the real client.
    return request.client.host if request.client else "unknown"


def ensure_email(request: Request) -> None:
    """503 first when mail is not configured (SMTP_HOST empty), then the Origin check."""
    if not settings_of(request).email_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Email is not available")


def too_many() -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try later")


def check_origin(request: Request) -> None:
    """Block cross-site writes: when an Origin header is present it must be allowed."""
    if request.method not in UNSAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin and origin not in settings_of(request).allowed_origins:
        audit.warning("blocked origin=%s ip=%s", origin, client_ip(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin not allowed")


@dataclass(frozen=True)
class AuthSession:
    user: User
    token: str  # the access token (CSRF is bound to it)
    sid: str | None = None  # the session row (None: a token issued before sessions existed)


def current_session(request: Request, db: Session = Depends(get_db)) -> AuthSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(token)
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated") from None
    user = db.get(User, payload.user_id)
    # Legacy tokens carry no ver and stay valid until they expire.
    if user is None or (payload.ver is not None and payload.ver != user.token_version):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if payload.sid is not None:  # a sid whose row is gone or revoked is dead (a sid-less legacy token is not)
        row = usersessions.live_session(db, payload.sid, user.id)
        if row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
        usersessions.touch(db, row)
    return AuthSession(user=user, token=token, sid=payload.sid)


def csrf_session(
    request: Request,
    session: AuthSession = Depends(current_session),
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> AuthSession:
    if not csrf_valid(x_csrf_token, session.token):
        audit.warning("csrf failed user=%r ip=%s", session.user.username, client_ip(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    return session


def ensure_reauth(request: Request, user: User, password: str | None) -> None:
    """Sensitive actions need proof that the account owner is present.

    - password account: a valid fresh proof, or the password (throttled; a wrong one is 403);
    - account without a password: a valid fresh proof, else 401 {detail, reauth: [methods]} (app.reauth).
      An account with no way to produce a proof at all (e.g. voice/webcam only) is let through: it could
      never act otherwise.
    """
    if has_fresh_proof(request, user):
        return
    if not user.has_password:
        methods = available_methods(request, user)
        if methods:
            raise ReauthRequired(methods)
        return
    throttle = request.app.state.reauth_throttle
    key = str(user.id)
    if throttle.is_blocked(key):
        raise too_many()
    if not verify_password(password or "", user.password_hash):
        throttle.record(key)
        audit.warning("reauth failed user=%r ip=%s", user.username, client_ip(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, BAD_REAUTH)
