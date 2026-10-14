from fastapi import Depends, HTTPException, Request, status

from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload


def writer(request: Request, user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Authenticated user within the per-user write limit (60 per minute)."""
    if not request.app.state.limiter.allow(user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Bạn thao tác quá nhanh, hãy thử lại sau")
    return user


def db_reader(request: Request, user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Authenticated user within the (more generous) read limit of the database browser."""
    if not request.app.state.read_limiter.allow(user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Bạn thao tác quá nhanh, hãy thử lại sau")
    return user
