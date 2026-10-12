"""Issuing and clearing session cookies (access + refresh) and the CSRF token."""

from fastapi import HTTPException, Response, status

from app.config import Settings
from app.models import User
from app.schemas import MfaRequired, SessionOut
from app.tokens import create_mfa_token, create_refresh_token, csrf_token
from sn_shared import COOKIE_NAME, create_token

REFRESH_COOKIE = "sn_refresh"
# The refresh cookie is only sent to the auth API; this is the browser-visible path behind the gateway.
REFRESH_PATH = "/api/center/auth"


def _cookie_options(settings: Settings, path: str) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": settings.cookie_secure, "path": path}


def issue_session(response: Response, user: User, settings: Settings) -> SessionOut:
    """Set both cookies for the user's current token_version and return the Session body."""
    access = create_token(
        user.id, user.username, ttl_seconds=settings.access_minutes * 60, role=user.role, ver=user.token_version
    )
    refresh = create_refresh_token(user.id, user.token_version, settings.refresh_days * 86400)
    response.set_cookie(COOKIE_NAME, access, max_age=settings.access_minutes * 60, **_cookie_options(settings, "/"))
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=settings.refresh_days * 86400, **_cookie_options(settings, REFRESH_PATH)
    )
    return SessionOut(id=user.id, username=user.username, role=user.role, csrf_token=csrf_token(access))


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(COOKIE_NAME, **_cookie_options(settings, "/"))
    response.delete_cookie(REFRESH_COOKIE, **_cookie_options(settings, REFRESH_PATH))


def start_login(response: Response, user: User, settings: Settings, biometrics_available: bool) -> SessionOut | MfaRequired:
    """After the primary factor (password or Google).

    Default: a session. Only an account that opted in (`biometric_2fa`) AND has samples gets an
    MFA challenge (no cookies yet). If such an account signs in while biometrics are switched off
    server-wide we FAIL CLOSED with 503: a factor the user asked for is never silently skipped.
    """
    if user.biometric_2fa and user.has_biometrics:
        if not biometrics_available:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Biometrics are not available")
        return MfaRequired(mfa_token=create_mfa_token(user.id, user.token_version))
    return issue_session(response, user, settings)
