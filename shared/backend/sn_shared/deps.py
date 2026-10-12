from fastapi import HTTPException, Request, status

from sn_shared.security import AuthError, TokenPayload, payload_from_cookies


def get_current_user(request: Request) -> TokenPayload:
    """FastAPI dependency: the authenticated user from the auth cookie, or 401."""
    try:
        return payload_from_cookies(request.cookies)
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated") from None
