"""Issuing and clearing session cookies (access + refresh) and the CSRF token."""

from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import usersessions
from app.config import Settings
from app.models import User
from app.schemas import MfaRequired, SessionOut
from app.tokens import create_mfa_token, create_refresh_token, csrf_token
from sn_shared import COOKIE_NAME, create_token

TOTP_FACTOR = "totp"
BIOMETRIC_FACTOR = "biometric"
REFRESH_COOKIE = "sn_refresh"
FRESH_COOKIE = "sn_fresh"  # proof of a recent re-authentication (see app.reauth)
# The refresh cookie is only sent to the auth API; this is the browser-visible path behind the gateway.
REFRESH_PATH = "/api/center/auth"


def cookie_options(settings: Settings, path: str) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": settings.cookie_secure, "path": path}


def issue_session(response: Response, user: User, settings: Settings, sid: str) -> SessionOut:
    """Set both cookies for the user's current token_version and session `sid`; return the Session body."""
    access = create_token(
        user.id, user.username, ttl_seconds=settings.access_minutes * 60, role=user.role, ver=user.token_version,
        sid=sid,
    )
    refresh = create_refresh_token(user.id, user.token_version, settings.refresh_days * 86400, sid=sid)
    response.set_cookie(COOKIE_NAME, access, max_age=settings.access_minutes * 60, **cookie_options(settings, "/"))
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=settings.refresh_days * 86400, **cookie_options(settings, REFRESH_PATH)
    )
    return SessionOut(id=user.id, username=user.username, role=user.role, csrf_token=csrf_token(access))


def begin_session(
    response: Response, request: Request, db: Session, user: User, settings: Settings, method: str
) -> SessionOut:
    """A new sign-in: record the device (`method` = the primary factor used) and issue its cookies."""
    sid = usersessions.create(db, request, user.id, method, settings)
    return issue_session(response, user, settings, sid)


def reissue_session(
    response: Response, request: Request, db: Session, user: User, settings: Settings, current_sid: str | None
) -> SessionOut:
    """New cookies for the SAME session after a token_version bump (the caller used keep_sid=current_sid).

    A legacy token (no sid) is upgraded to a session row with method "refresh".
    """
    if current_sid is None:
        return begin_session(response, request, db, user, settings, "refresh")
    return issue_session(response, user, settings, current_sid)


def clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(COOKIE_NAME, **cookie_options(settings, "/"))
    response.delete_cookie(REFRESH_COOKIE, **cookie_options(settings, REFRESH_PATH))
    response.delete_cookie(FRESH_COOKIE, **cookie_options(settings, REFRESH_PATH))


def start_login(
    response: Response, user: User, settings: Settings, biometrics_available: bool, *,
    request: Request, db: Session, method: str,
) -> SessionOut | MfaRequired:  # fmt: skip
    """After the primary factor (password or Google).

    Default: a session. An account with TOTP enabled, or one that opted in to biometrics
    (`biometric_2fa`) AND has samples, gets an MFA challenge (no cookies yet) listing the usable
    `factors`; any one listed factor completes the login. A biometric-only account signing in while
    biometrics are switched off server-wide FAILS CLOSED with 503: a factor the user asked for is
    never silently skipped. With TOTP enabled the only factor is "totp" (a biometric is not offered).
    `method` is the primary factor; it travels in the mfa token to become the session's method.
    """
    if user.totp_enabled:
        return totp_challenge(user, method)  # TOTP alone: a spoofable biometric never substitutes for it
    if user.biometric_2fa and user.has_biometrics:
        if not biometrics_available:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Biometrics are not available")
        token = create_mfa_token(user.id, user.token_version, method=method)
        return MfaRequired(mfa_token=token, factors=[BIOMETRIC_FACTOR])
    return begin_session(response, request, db, user, settings, method)


def totp_challenge(user: User, method: str) -> MfaRequired:
    token = create_mfa_token(user.id, user.token_version, method=method)
    return MfaRequired(mfa_token=token, factors=[TOTP_FACTOR])


def finish_primary_biometric_login(
    response: Response, user: User, settings: Settings, *, request: Request, db: Session, method: str
) -> SessionOut | MfaRequired:  # fmt: skip
    """Voice/webcam sign-in is a primary factor only: an account with TOTP still owes the second step."""
    if user.totp_enabled:
        return totp_challenge(user, method)
    return begin_session(response, request, db, user, settings, method)
