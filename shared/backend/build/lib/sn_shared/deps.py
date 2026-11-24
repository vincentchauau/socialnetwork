"""Who may call what: one rule for every route, applied where its router is mounted.

`require_groups` decides by the caller's group and the action the HTTP method means (GET = R, POST = C,
PATCH/PUT = U, DELETE = D). `require_users` narrows the call to some user ids; by default every signed-in user passes.
A call is allowed only when both pass. Owner checks stay in the handlers (`sn_shared.access`).
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from starlette.requests import HTTPConnection

from sn_shared.security import AuthError, TokenPayload, payload_from_cookies

GROUP_USER = "user"
GROUP_MODERATOR = "moderator"
GROUP_ADMIN = "admin"
GROUPS = (GROUP_USER, GROUP_MODERATOR, GROUP_ADMIN)  # the platform groups a token (users.group) can carry

ACTION_BY_METHOD = {"GET": "R", "HEAD": "R", "POST": "C", "PUT": "U", "PATCH": "U", "DELETE": "D"}
WEBSOCKET_ACTION = "R"  # opening a socket reads; the messages it carries are checked by the handler


def get_current_user(request: HTTPConnection) -> TokenPayload:
    """FastAPI dependency: the authenticated user from the auth cookie, or 401."""
    try:
        return payload_from_cookies(request.cookies)
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated") from None


def action_of(connection: HTTPConnection) -> str:
    """The CRUD letter a request asks for: C, R, U or D."""
    method = getattr(connection, "method", None)
    return ACTION_BY_METHOD.get(method, WEBSOCKET_ACTION) if method else WEBSOCKET_ACTION


def require_groups(*, admin: str = "", moderator: str = "", user: str = "", public: bool = False) -> Callable[..., object]:
    """Dependency factory: the letters each group may use (e.g. admin="CRUD", moderator="CRU", user="R").

    `public=True` marks a route that needs no sign-in (health, sign-in and sign-up). Carries `access_groups`
    (group -> letters) so tests can read the rule of every route.
    """
    allowed = {GROUP_ADMIN: admin, GROUP_MODERATOR: moderator, GROUP_USER: user}

    def dependency(connection: HTTPConnection) -> TokenPayload | None:
        if public:
            return None
        user_payload = get_current_user(connection)
        if action_of(connection) not in allowed.get(user_payload.group, ""):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return user_payload

    dependency.access_groups = dict(allowed)  # type: ignore[attr-defined]
    dependency.public = public  # type: ignore[attr-defined]
    return dependency


def require_users(*user_ids: int) -> Callable[..., object]:
    """Dependency factory: only these user ids may call. No ids (the default) means every signed-in user may."""
    allowed = frozenset(user_ids)

    def dependency(connection: HTTPConnection) -> TokenPayload | None:
        if not allowed:
            return None
        user_payload = get_current_user(connection)
        if user_payload.user_id not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return user_payload

    dependency.access_users = allowed  # type: ignore[attr-defined]
    return dependency


def access_dependencies(*, admin: str = "", moderator: str = "", user: str = "", public: bool = False) -> list:
    """The two gates every route carries, ready for `include_router(..., dependencies=...)`."""
    return [Depends(require_groups(admin=admin, moderator=moderator, user=user, public=public)), Depends(require_users())]


def ensure_group(user: TokenPayload, *groups: str, detail: str = "Forbidden") -> TokenPayload:
    """The user when the token group is one of `groups`, else 403 (for a check inside a handler)."""
    if user.group not in groups:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail)
    return user
