"""Step-up (fresh) re-authentication.

A password account proves itself with its password (or a fresh proof); an account WITHOUT a password needs a
fresh proof: the `sn_fresh` cookie, a signed token (`typ="fresh"`, 5 minutes) for one user AND one session,
obtained with a passkey, the linked Google account, or a code mailed to the VERIFIED email.

The cookie is HttpOnly, SameSite=Lax and limited to the auth API path; logout clears it, and bumping the
token version (password/TOTP changes) invalidates it because the token carries `ver`.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from api.center.config import Settings
from api.center.methods import has_verified_email
from api.center.models import User
from api.center.schemas import FreshOut
from api.center.sessions import FRESH_COOKIE, REFRESH_PATH, cookie_options
from api.center.tokens import create_fresh_token, decode_claims
from sn_shared import COOKIE_NAME
from sn_shared.security import AuthError, decode_token

import logging
logger = logging.getLogger(__name__)

FRESH_TTL_SECONDS = 5 * 60
PASSWORD, PASSKEY, GOOGLE, EMAIL = "password", "passkey", "google", "email"
REAUTH_REQUIRED = "Re-authentication required"
REAUTH_FAILED = "Re-authentication failed"


class ReauthRequired(Exception):
    """A sensitive call came without proof; rendered as 401 {detail, reauth: [methods]} (see `reauth_response`)."""

    def __init__(self, methods: list[str]) -> None:
        try:
            super().__init__(REAUTH_REQUIRED)
            self.methods = methods
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise


def reauth_response(_: Request, exc: ReauthRequired) -> JSONResponse:
    try:
        return JSONResponse({"detail": REAUTH_REQUIRED, "reauth": exc.methods}, status_code=401)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("reauth_response failed")
        raise


def available_methods(request: Request, user: User) -> list[str]:
    """What this user can use right now, in display order (a method the server cannot run is not offered)."""
    try:
        state = request.app.state
        methods = []
        if user.has_password:
            methods.append(PASSWORD)
        if user.passkeys:
            methods.append(PASSKEY)
        if user.google_linked and state.google_verifier is not None:
            methods.append(GOOGLE)
        if has_verified_email(user) and state.settings.email_enabled:
            methods.append(EMAIL)
        return methods
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("available_methods failed")
        raise


def current_sid(request: Request) -> str | None:
    """The sid of the access token on this request (already validated by the auth dependency)."""
    try:
        return decode_token(request.cookies.get(COOKIE_NAME, "")).sid
    except AuthError:
        return None


def has_fresh_proof(request: Request, user: User) -> bool:
    """A valid `sn_fresh` for THIS user and THIS session (no sid on either side = a legacy session)."""
    token = request.cookies.get(FRESH_COOKIE)
    if not token:
        return False
    try:
        claims = decode_claims(token, "fresh")
    except AuthError:
        return False
    return (
        int(claims["sub"]) == user.id
        and int(claims["ver"]) == user.token_version
        and claims.get("sid") == current_sid(request)
    )


def set_fresh(response: Response, request: Request, user: User, settings: Settings) -> FreshOut:
    try:
        token = create_fresh_token(user.id, user.token_version, FRESH_TTL_SECONDS, current_sid(request))
        response.set_cookie(FRESH_COOKIE, token, max_age=FRESH_TTL_SECONDS, **cookie_options(settings, REFRESH_PATH))
        return FreshOut(fresh_until=datetime.now(timezone.utc) + timedelta(seconds=FRESH_TTL_SECONDS))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("set_fresh failed")
        raise
