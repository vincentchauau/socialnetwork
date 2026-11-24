import pytest

from sn_shared import COOKIE_NAME, decode_token
from tests.center.helpers import CREDS, STRONG, csrf, register, set_cookies


def test_register_creates_user_and_sets_cookies(client):
    response = client.post("/auth/register", json=CREDS)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "Alice"
    assert body["group"] == "user"
    assert body["csrf_token"]
    assert "password" not in response.text
    cookies = set_cookies(response)
    assert cookies[COOKIE_NAME].startswith(f"{COOKIE_NAME}=")
    assert set(cookies) == {"sn_token", "sn_refresh"}


def test_cookie_flags(client):
    cookies = set_cookies(client.post("/auth/register", json=CREDS))
    access, refresh = cookies["sn_token"], cookies["sn_refresh"]
    for line in (access, refresh):
        assert "HttpOnly" in line and "SameSite=lax" in line
        assert "Secure" not in line
    assert "Path=/;" in access + ";" and "Max-Age=3600" in access
    assert "Path=/api/center/auth" in refresh and f"Max-Age={14 * 86400}" in refresh


def test_secure_flag_and_ttls_follow_env(monkeypatch):
    from fastapi.testclient import TestClient

    from api.center.main import create_app

    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "5")
    monkeypatch.setenv("REFRESH_DAYS", "2")
    cookies = set_cookies(TestClient(create_app("sqlite://")).post("/auth/register", json=CREDS))
    assert "Secure" in cookies["sn_token"] and "Secure" in cookies["sn_refresh"]
    assert "Max-Age=300" in cookies["sn_token"]
    assert f"Max-Age={2 * 86400}" in cookies["sn_refresh"]


def test_access_token_claims_stay_compatible_with_other_services(client):
    session = register(client)
    payload = decode_token(client.cookies.get(COOKIE_NAME))
    assert (payload.user_id, payload.username, payload.group, payload.ver) == (
        session["id"], "Alice", "user", 0,
    )  # fmt: skip


def test_role_in_jwt_follows_the_database(client):
    from api.center.models import User

    register(client)
    with client.app.state.session_factory() as db:
        db.query(User).update({"group": "admin"})
        db.commit()
    client.cookies.clear()
    assert client.post("/auth/login", json=CREDS).json()["group"] == "admin"
    assert decode_token(client.cookies.get(COOKIE_NAME)).group == "admin"


def test_register_duplicate_username_returns_409(client):
    client.post("/auth/register", json=CREDS)
    response = client.post("/auth/register", json={**CREDS, "username": "ALICE"})
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("password", "fragment"),
    [
        ("short", "at least 8"),
        ("p" * 129, "at most 128"),
        ("aaaaaaaabbbb", "special character"),
        ("alllower-case1!", "uppercase letter"),
        ("ALLUPPER-CASE1!", "special character"),
        ("No-digits-here!", "special character"),
        ("Password123!", "too common"),
        ("P@ssw0rd", "too common"),
        ("Alice-alice-1", None),
    ],
)
def test_register_password_policy(client, password, fragment):
    response = client.post("/auth/register", json={**CREDS, "password": password})
    if fragment is None:
        assert response.status_code == 201  # distinct from the username: allowed
        return
    assert response.status_code == 422
    assert fragment in response.json()["detail"]


def test_register_accepts_password_equal_to_username(client):
    response = client.post("/auth/register", json={"username": "long-name1", "password": "Long-Name1"})
    assert response.status_code == 201


@pytest.mark.parametrize("name", ["a b", "ab", "x" * 33, "bad/name", "emojié"])
def test_register_rejects_bad_username(client, name):
    response = client.post("/auth/register", json={**CREDS, "username": name})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_register_accepts_dots_dashes_and_keeps_case(client):
    response = client.post("/auth/register", json={**CREDS, "username": "  Al.ice-1_x "})
    assert response.json()["username"] == "Al.ice-1_x"


def test_login_with_correct_password_authenticates_me(client):
    register(client)
    client.cookies.clear()

    login = client.post("/auth/login", json=CREDS)
    me = client.get("/auth/me")

    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json() == {
        "id": login.json()["id"], "username": "Alice", "group": "user", "email": None, "email_verified": False,
        "has_password": True, "google_linked": False, "voice_login": False, "webcam_login": False,
        "has_audio": False, "has_face": False, "require_biometric_2fa": False, "passkey_count": 0, "passkeys": [],
            "totp_enabled": False, "recovery_codes_left": 0, "phone": None, "phone_verified": False,
        "csrf_token": login.json()["csrf_token"], "username_changed_at": None, "can_rename_after": None,
    }  # fmt: skip


def test_login_with_wrong_password_returns_401(client):
    register(client)
    response = client.post("/auth/login", json={**CREDS, "password": "wrong-password"})
    assert response.status_code == 401
    assert "sn_token" not in set_cookies(response)


def test_login_unknown_user_returns_same_401(client):
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_login_with_malformed_username_is_the_same_401(client):
    response = client.post("/auth/login", json={"username": "no spaces!", "password": "whatever-pass"})
    assert (response.status_code, response.json()["detail"]) == (401, "Invalid username or password")


def test_me_without_cookie_returns_401(client):
    assert client.get("/auth/me").status_code == 401


def test_config_is_public_and_reports_features(client):
    assert client.get("/auth/config").json() == {"google_client_id": None, "biometrics_enabled": False, "email_enabled": False, "phone_enabled": False, "liveness_enabled": False, "liveness_required": False}


def test_config_reports_google_client_id(monkeypatch):
    from fastapi.testclient import TestClient

    from api.center.main import create_app

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.example")
    config = TestClient(create_app("sqlite://")).get("/auth/config").json()
    assert config["google_client_id"] == "abc.apps.example"


def test_logout_requires_csrf_and_revokes_the_session(client):
    session = register(client)
    assert client.post("/auth/logout").status_code == 403
    response = client.post("/auth/logout", headers=csrf(session))
    assert response.status_code == 204
    cookies = set_cookies(response)
    assert "Max-Age=0" in cookies["sn_token"] and "Max-Age=0" in cookies["sn_refresh"]
    assert "Path=/api/center/auth" in cookies["sn_refresh"]


def test_old_access_token_is_dead_after_logout(client):
    session = register(client)
    stolen = client.cookies.get(COOKIE_NAME)
    client.post("/auth/logout", headers=csrf(session))
    client.cookies.set(COOKIE_NAME, stolen, path="/")
    assert client.get("/auth/me").status_code == 401


def test_legacy_token_without_ver_is_accepted(client):
    from sn_shared import create_token

    session = register(client)
    client.cookies.set(COOKIE_NAME, create_token(session["id"], "alice"), path="/")
    assert client.get("/auth/me").status_code == 200


def test_token_for_deleted_user_is_rejected(client):
    from sn_shared import create_token

    client.cookies.set(COOKIE_NAME, create_token(999, "ghost"), path="/")
    assert client.get("/auth/me").status_code == 401


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "redis": "off"}


def test_strong_password_constant_is_acceptable():
    from api.center.passwords import password_problem

    assert password_problem(STRONG) is None
