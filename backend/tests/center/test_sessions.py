import time

from api.center.tokens import create_refresh_token, csrf_token, csrf_valid
from sn_shared import COOKIE_NAME, create_token
from tests.center.helpers import CREDS, STRONG, cookie_value, csrf, forge, refresh_with, register, set_cookies


def login_tokens(client):
    """Log in and return (session, access, refresh) from the Set-Cookie headers."""
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 200
    return response.json(), cookie_value(response, "sn_token"), cookie_value(response, "sn_refresh")


# --- refresh ---------------------------------------------------------------------------------


def test_refresh_reissues_both_cookies(client):
    response = client.post("/auth/register", json=CREDS)
    refresh = cookie_value(response, "sn_refresh")

    again = refresh_with(client, refresh)

    assert again.status_code == 200
    assert again.json()["username"] == "Alice" and again.json()["csrf_token"]
    assert set(set_cookies(again)) == {"sn_token", "sn_refresh"}


def test_refresh_needs_a_cookie(client):
    response = refresh_with(client, None)
    assert response.status_code == 401
    assert "Max-Age=0" in set_cookies(response)["sn_refresh"]


def test_refresh_ignores_an_access_token_in_the_refresh_slot(client):
    register(client)
    assert refresh_with(client, client.cookies.get(COOKIE_NAME)).status_code == 401


def test_refresh_token_cannot_be_used_as_an_access_token(client):
    session = register(client)
    refresh = create_refresh_token(session["id"], 0, 600)
    client.cookies.set(COOKIE_NAME, refresh, path="/")
    assert client.get("/auth/me").status_code == 401


def test_token_of_an_unknown_kind_cannot_be_used_as_refresh_or_access(client):
    session = register(client)
    odd = forge({"sub": str(session["id"]), "typ": "other", "ver": 0})
    assert refresh_with(client, odd).status_code == 401
    client.cookies.set(COOKIE_NAME, odd, path="/")
    assert client.get("/auth/me").status_code == 401


def test_refresh_rejects_expired_tampered_and_foreign_tokens(client):
    session = register(client)
    expired = forge({"sub": str(session["id"]), "typ": "refresh", "ver": 0, "exp": int(time.time()) - 5})
    tampered = create_refresh_token(session["id"], 0, 600)[:-3] + "abc"
    foreign = forge({"sub": str(session["id"]), "typ": "refresh", "ver": 0}, secret="z" * 40)
    no_ver = forge({"sub": str(session["id"]), "typ": "refresh"})
    no_typ = forge({"sub": str(session["id"]), "ver": 0})
    for token in (expired, tampered, foreign, no_ver, no_typ, "not-a-jwt"):
        response = refresh_with(client, token)
        assert response.status_code == 401, token
        assert "Max-Age=0" in set_cookies(response)["sn_token"]


def test_refresh_rejects_deleted_user(client):
    refresh = create_refresh_token(4242, 0, 600)
    assert refresh_with(client, refresh).status_code == 401


def test_refresh_is_throttled_per_address(client):
    register(client)
    codes = [refresh_with(client, "junk").status_code for _ in range(62)]
    assert codes[0] == 401 and codes[-1] == 429


# --- revocation via token_version ------------------------------------------------------------


def test_logout_revokes_refresh_and_access_tokens(client):
    session = register(client)
    access, refresh = client.cookies.get(COOKIE_NAME), create_refresh_token(session["id"], 0, 600)
    assert client.post("/auth/logout", headers=csrf(session)).status_code == 204

    assert refresh_with(client, refresh).status_code == 401
    client.cookies.set(COOKIE_NAME, access, path="/")
    assert client.get("/auth/me").status_code == 401


def test_password_change_revokes_other_sessions_but_keeps_this_one(client):
    register(client)
    session, old_access, old_refresh = login_tokens(client)

    response = client.post(
        "/auth/me/password",
        json={"current_password": CREDS["password"], "new_password": STRONG},
        headers=csrf(session),
    )

    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 200  # fresh cookies were set
    assert refresh_with(client, old_refresh).status_code == 401
    client.cookies.set(COOKIE_NAME, old_access, path="/")
    assert client.get("/auth/me").status_code == 401


def test_other_services_still_accept_the_access_token_until_it_expires(client):
    """Documented limit: only center checks ver."""
    from sn_shared import decode_token

    register(client)
    session, old_access, _ = login_tokens(client)
    client.post("/auth/logout", headers=csrf(session))
    assert decode_token(old_access).username == "Alice"


# --- CSRF -------------------------------------------------------------------------------------


def test_csrf_helpers_bind_to_the_token():
    token = create_token(1, "a")
    good = csrf_token(token)
    assert csrf_valid(good, token)
    assert not csrf_valid(good, create_token(1, "b"))
    assert not csrf_valid(None, token) and not csrf_valid("", token)
    assert csrf_token(token) != token


def test_csrf_missing_or_wrong_is_403(client):
    session = register(client)
    body = {"current_password": CREDS["password"], "new_password": STRONG}
    assert client.post("/auth/me/password", json=body).status_code == 403
    assert client.post("/auth/me/password", json=body, headers={"X-CSRF-Token": "nope"}).status_code == 403
    assert client.post("/auth/me/password", json=body, headers=csrf(session)).status_code == 200


def test_csrf_token_is_returned_by_me_and_matches_the_session(client):
    session = register(client)
    assert client.get("/auth/me").json()["csrf_token"] == session["csrf_token"]


# --- Origin -----------------------------------------------------------------------------------


def test_foreign_origin_is_blocked_on_writes(client):
    response = client.post("/auth/login", json=CREDS, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_default_origin_and_missing_origin_are_allowed(client):
    register(client)
    assert client.post("/auth/login", json=CREDS, headers={"Origin": "http://localhost:8080"}).status_code == 200
    assert client.post("/auth/login", json=CREDS).status_code == 200


def test_reads_are_not_origin_checked(client):
    assert client.get("/auth/config", headers={"Origin": "https://evil.example"}).status_code == 200


def test_allowed_origins_env_is_honoured(monkeypatch):
    from fastapi.testclient import TestClient

    from api.center.main import create_app

    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    client = TestClient(create_app("sqlite://"))
    assert client.post("/auth/login", json=CREDS, headers={"Origin": "https://b.example"}).status_code == 401
    assert client.post("/auth/login", json=CREDS, headers={"Origin": "http://localhost:8080"}).status_code == 403
