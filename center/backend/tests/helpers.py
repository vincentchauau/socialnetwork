"""Shared test helpers (plain functions, importable from any test module)."""

from sn_shared.security import ALGORITHM, ISSUER, get_jwt_secret

CREDS = {"username": "Alice", "password": "s3cret-pass"}
STRONG = "correct-horse-battery"


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
    return jwt.encode({**base, **claims}, secret or get_jwt_secret(), algorithm=ALGORITHM)
