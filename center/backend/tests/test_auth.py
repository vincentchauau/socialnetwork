from sn_shared import COOKIE_NAME

CREDS = {"username": "Alice", "password": "s3cret-pass"}


def test_register_creates_user_and_sets_http_only_cookie(client):
    response = client.post("/auth/register", json=CREDS)

    assert response.status_code == 201
    assert response.json()["username"] == "alice"
    assert "password" not in response.text
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie


def test_register_duplicate_username_returns_409(client):
    client.post("/auth/register", json=CREDS)
    response = client.post("/auth/register", json={**CREDS, "username": "ALICE"})
    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post("/auth/register", json={**CREDS, "password": "short"})
    assert response.status_code == 422


def test_register_rejects_overlong_password(client):
    response = client.post("/auth/register", json={**CREDS, "password": "p" * 73})
    assert response.status_code == 422


def test_register_rejects_bad_username(client):
    response = client.post("/auth/register", json={**CREDS, "username": "a b"})
    assert response.status_code == 422


def test_login_with_correct_password_authenticates_me(client):
    client.post("/auth/register", json=CREDS)
    client.cookies.clear()

    assert client.post("/auth/login", json=CREDS).status_code == 200
    me = client.get("/auth/me")

    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_login_with_wrong_password_returns_401(client):
    client.post("/auth/register", json=CREDS)
    response = client.post("/auth/login", json={**CREDS, "password": "wrong-password"})
    assert response.status_code == 401


def test_login_unknown_user_returns_same_401(client):
    response = client.post("/auth/login", json=CREDS)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_me_without_cookie_returns_401(client):
    assert client.get("/auth/me").status_code == 401


def test_logout_clears_session(client):
    client.post("/auth/register", json=CREDS)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
