from sqlalchemy import select

from app.models import User
from tests.helpers import CREDS, STRONG, csrf, refresh_with, register, cookie_value, grant_fresh


def delete_account(client, session, body=None):
    return client.request("DELETE", "/auth/me", json=body, headers=csrf(session))


def test_change_password_requires_the_current_password(client):
    session = register(client)
    body = {"current_password": "wrong-password", "new_password": STRONG}
    response = client.post("/auth/me/password", json=body, headers=csrf(session))
    assert response.status_code == 403
    assert response.json()["detail"] == "Incorrect password"


def test_change_password_applies_policy_and_new_login_works(client):
    session = register(client)
    weak = {"current_password": CREDS["password"], "new_password": "short"}
    assert client.post("/auth/me/password", json=weak, headers=csrf(session)).status_code == 422

    ok = {"current_password": CREDS["password"], "new_password": STRONG}
    fresh = client.post("/auth/me/password", json=ok, headers=csrf(session)).json()
    assert fresh["csrf_token"] != session["csrf_token"]

    client.cookies.clear()
    assert client.post("/auth/login", json=CREDS).status_code == 401
    assert client.post("/auth/login", json={**CREDS, "password": STRONG}).status_code == 200


def test_reauth_failures_are_throttled(client):
    session = register(client)
    body = {"current_password": "wrong-password", "new_password": STRONG}
    codes = [client.post("/auth/me/password", json=body, headers=csrf(session)).status_code for _ in range(7)]
    assert codes[:5] == [403] * 5 and codes[-1] == 429


def test_delete_account_needs_csrf_and_password(client):
    session = register(client)
    assert client.request("DELETE", "/auth/me").status_code == 403
    assert delete_account(client, session).status_code == 403  # password missing
    assert delete_account(client, session, {"password": "wrong-password"}).status_code == 403

    response = delete_account(client, session, {"password": CREDS["password"]})

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/login", json=CREDS).status_code == 401


def test_delete_account_revokes_refresh_tokens(client):
    register(client)
    login = client.post("/auth/login", json=CREDS)
    session, refresh = login.json(), cookie_value(login, "sn_refresh")
    delete_account(client, session, {"password": CREDS["password"]})
    assert refresh_with(client, refresh).status_code == 401


def test_google_only_account_can_set_a_first_password_without_current(google_client):
    client = google_client
    session = client.post("/auth/google", json={"id_token": "sub-1|first.user@example.com"}).json()
    grant_fresh(google_client)
    me = client.get("/auth/me").json()
    assert me["has_password"] is False

    response = client.post("/auth/me/password", json={"new_password": STRONG}, headers=csrf(session))

    assert response.status_code == 200
    assert client.get("/auth/me").json()["has_password"] is True
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": "first.user", "password": STRONG}).status_code == 200


def test_password_account_reads_back_in_the_database(client):
    register(client)
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("scrypt$") and user.role == "user" and user.token_version == 0
