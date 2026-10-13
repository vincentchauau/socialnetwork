"""Shared test helpers (plain functions, importable from any test module)."""

from app.tokens import create_fresh_token
from sn_shared.security import INTERNAL_ALGORITHM, ISSUER, decode_token, get_jwt_secret

CREDS = {"username": "Alice", "password": "S3cret-Pass"}
STRONG = "Correct-Horse-Battery1"


def register(client, creds=CREDS):
    response = client.post("/auth/register", json=creds)
    assert response.status_code == 201, response.text
    return response.json()


def csrf(session: dict) -> dict:
    """Header for state-changing requests, from a Session/Me body."""
    return {"X-CSRF-Token": session["csrf_token"]}


def set_cookies(response) -> dict[str, str]:
    """name -> raw Set-Cookie header line."""
    lines = response.headers.get_list("set-cookie")
    return {line.split("=", 1)[0]: line for line in lines}


def cookie_value(response, name: str) -> str:
    line = set_cookies(response)[name]
    return line.split("=", 1)[1].split(";", 1)[0]


def refresh_with(client, token: str | None, **kwargs):
    """POST /auth/refresh sending ONLY the refresh cookie (its browser path is /api/center/auth)."""
    headers = {"Cookie": f"sn_refresh={token}"} if token else {}
    return client.post("/auth/refresh", headers=headers, **kwargs)


def forge(claims: dict, secret: str | None = None) -> str:
    import jwt

    base = {"iss": ISSUER, "exp": 4102444800}
    return jwt.encode({**base, **claims}, secret or get_jwt_secret(), algorithm=INTERNAL_ALGORITHM)


def grant_fresh(client, ttl: int = 300) -> None:
    """Shortcut for the step-up proof: put a valid `sn_fresh` for the client's current session in its jar.

    (Real browsers get it from /auth/reauth/*; its path is /api/center/auth, the jar here gets path "/".)
    """
    payload = decode_token(client.cookies.get("sn_token"))
    client.cookies.set("sn_fresh", create_fresh_token(payload.user_id, payload.ver or 0, ttl, payload.sid), path="/")
