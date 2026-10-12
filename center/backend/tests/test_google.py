import pytest
from sqlalchemy import select

from app.google_auth import GoogleAuthError, make_google_verifier
from app.handles import base_handle, unique_handle
from app.models import User
from app.passwords import NO_PASSWORD
from tests.helpers import CREDS, csrf, register, grant_fresh


def google_login(client, token="sub-1|jane.doe@example.com"):
    return client.post("/auth/google", json={"id_token": token})


def test_not_configured_returns_503(client):
    response = google_login(client)
    assert response.status_code == 503
    assert response.json()["detail"] == "Google sign-in is not configured"


def test_first_login_creates_a_google_only_account(google_client):
    response = google_login(google_client)

    assert response.status_code == 200
    assert response.json()["username"] == "jane.doe"
    me = google_client.get("/auth/me").json()
    assert (me["email"], me["has_password"], me["google_linked"]) == ("jane.doe@example.com", False, True)
    with google_client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash == NO_PASSWORD and user.google_sub == "sub-1"


def test_second_login_finds_the_same_user_by_sub(google_client):
    first = google_login(google_client).json()
    google_client.cookies.clear()
    second = google_login(google_client, "sub-1|changed.address@example.com").json()
    assert first["id"] == second["id"]


def test_google_only_account_cannot_log_in_with_a_password(google_client):
    google_login(google_client)
    for password in ("!", "", "anything-at-all"):
        response = google_client.post("/auth/login", json={"username": "jane.doe", "password": password})
        assert response.status_code == 401


def test_handle_collision_gets_a_numeric_suffix_and_never_the_domain(google_client):
    register(google_client, {"username": "jane.doe", "password": "s3cret-pass"})
    google_client.cookies.clear()
    handle = google_login(google_client).json()["username"]
    assert handle == "jane.doe2"
    assert "example" not in handle and "@" not in handle


def test_unverified_or_invalid_token_is_rejected(google_client):
    response = google_login(google_client, "bad-token")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Google token"
    assert google_client.get("/auth/me").status_code == 401


def test_failed_google_tokens_are_throttled_per_address(google_client):
    codes = [google_login(google_client, "bad-token").status_code for _ in range(22)]
    assert codes[0] == 401 and codes[-1] == 429


def test_does_not_auto_link_to_a_password_account_with_the_same_email(google_client):
    register(google_client)
    google_client.cookies.clear()
    google_login(google_client, "sub-9|alice@example.com")
    with google_client.app.state.session_factory() as db:
        assert {u.username for u in db.scalars(select(User))} == {"alice", "alice2"}


def test_email_already_used_is_not_stored_twice(google_client):
    google_login(google_client, "sub-1|dup@example.com")
    google_client.cookies.clear()
    google_login(google_client, "sub-2|dup@example.com")
    with google_client.app.state.session_factory() as db:
        emails = sorted(str(u.email) for u in db.scalars(select(User)))
    assert emails == ["None", "dup@example.com"]


def test_register_throttle_applies_to_google_account_creation(google_client):
    codes = [google_login(google_client, f"s{i}|user{i}@example.com").status_code for i in range(12)]
    assert codes[0] == 200 and codes[-1] == 429


# --- linking --------------------------------------------------------------------------------


def test_link_requires_csrf_and_password(google_client):
    session = register(google_client)
    body = {"id_token": "sub-5|alice.real@example.com", "password": CREDS["password"]}
    assert google_client.post("/auth/me/google", json=body).status_code == 403
    assert google_client.post("/auth/me/google", json={**body, "password": "wrong-password"}, headers=csrf(session)).status_code == 403

    response = google_client.post("/auth/me/google", json=body, headers=csrf(session))

    assert response.status_code == 200
    assert (response.json()["google_linked"], response.json()["email"]) == (True, "alice.real@example.com")
    google_client.cookies.clear()
    assert google_login(google_client, "sub-5|whatever@example.com").json()["username"] == "alice"


def test_link_duplicate_google_id_is_409(google_client):
    google_login(google_client, "sub-1|someone@example.com")
    google_client.cookies.clear()
    session = register(google_client)
    body = {"id_token": "sub-1|someone@example.com", "password": CREDS["password"]}
    assert google_client.post("/auth/me/google", json=body, headers=csrf(session)).status_code == 409


def test_link_with_invalid_token_is_401_and_unconfigured_is_503(google_client, client):
    session = register(google_client)
    body = {"id_token": "bad", "password": CREDS["password"]}
    assert google_client.post("/auth/me/google", json=body, headers=csrf(session)).status_code == 401
    google_client.app.state.google_verifier = None
    assert google_client.post("/auth/me/google", json=body, headers=csrf(session)).status_code == 503


# --- handle derivation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("Jane.Doe@x.com", "jane.doe"),
        ("j+tag@x.com", "jtag"),
        ("a@x.com", "a00"),
        ("+@x.com", "000"),
        ("über.user@x.com", "ber.user"),
        (("l" * 40) + "@x.com", "l" * 32),
    ],
)
def test_base_handle(email, expected):
    assert base_handle(email) == expected


def test_unique_handle_suffixes_and_respects_the_length_limit():
    taken = {"l" * 32, "l" * 31 + "2", "bob", "bob2"}
    assert unique_handle(("l" * 40) + "@x.com", taken.__contains__) == "l" * 31 + "3"
    assert unique_handle("bob@x.com", taken.__contains__) == "bob3"


# --- real verifier wrapper ----------------------------------------------------------------------


def test_real_verifier_rejects_garbage_tokens_without_network():
    verify = make_google_verifier("client-id")
    with pytest.raises(GoogleAuthError):
        verify("not-a-jwt")


def test_real_verifier_requires_verified_email(monkeypatch):
    from google.oauth2 import id_token

    verify = make_google_verifier("client-id")
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: {"sub": "1", "email": "a@b.co", "email_verified": False})
    with pytest.raises(GoogleAuthError):
        verify("tok")
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda *a, **k: {"sub": "1", "email": "A@B.co", "email_verified": True})
    identity = verify("tok")
    assert (identity.sub, identity.email) == ("1", "a@b.co")


# --- unlinking --------------------------------------------------------------------------------


def unlink(client, session, password=CREDS["password"]):
    return client.request(
        "DELETE", "/auth/me/google", json={"password": password} if password else None, headers=csrf(session)
    )


def test_unlink_needs_csrf_and_the_password(google_client):
    session = register(google_client)
    link = {"id_token": "sub-5|alice.real@example.com", "password": CREDS["password"]}
    google_client.post("/auth/me/google", json=link, headers=csrf(session))
    assert google_client.request("DELETE", "/auth/me/google", json={"password": CREDS["password"]}).status_code == 403
    assert unlink(google_client, session, "wrong-password").status_code == 403
    assert unlink(google_client, session, None).status_code == 403
    assert google_client.get("/auth/me").json()["google_linked"] is True


def test_unlink_clears_google_sub_and_email_and_password_login_still_works(google_client):
    session = register(google_client)
    link = {"id_token": "sub-5|alice.real@example.com", "password": CREDS["password"]}
    google_client.post("/auth/me/google", json=link, headers=csrf(session))

    response = unlink(google_client, session)

    assert response.status_code == 200
    body = response.json()
    assert (body["google_linked"], body["email"], body["has_password"]) == (False, None, True)
    with google_client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.google_sub is None and user.email is None
    google_client.cookies.clear()
    assert google_client.post("/auth/login", json=CREDS).status_code == 200
    # the old Google identity now creates a NEW account instead of reaching Alice
    assert google_login(google_client, "sub-5|alice.real@example.com").json()["username"] != "alice"


def test_google_only_account_cannot_unlink_its_only_method(google_client):
    session = google_login(google_client).json()
    grant_fresh(google_client)
    response = google_client.request("DELETE", "/auth/me/google", headers=csrf(session))
    assert response.status_code == 409 and response.json() == {"detail": "Keep at least one sign-in method"}
    assert google_client.get("/auth/me").json()["google_linked"] is True


def test_google_only_account_can_unlink_after_setting_a_password(google_client):
    session = google_login(google_client).json()
    grant_fresh(google_client)
    set_pw = google_client.post("/auth/me/password", json={"new_password": "correct-horse-battery"}, headers=csrf(session))
    assert set_pw.status_code == 200
    session = set_pw.json()
    response = google_client.request(
        "DELETE", "/auth/me/google", json={"password": "correct-horse-battery"}, headers=csrf(session)
    )
    assert response.status_code == 200 and response.json()["google_linked"] is False
    google_client.cookies.clear()
    login = google_client.post("/auth/login", json={"username": "jane.doe", "password": "correct-horse-battery"})
    assert login.status_code == 200


def test_unlink_when_nothing_is_linked_is_409(google_client):
    session = register(google_client)
    assert unlink(google_client, session).status_code == 409


def test_unlink_then_link_again(google_client):
    session = register(google_client)
    link = {"id_token": "sub-5|alice.real@example.com", "password": CREDS["password"]}
    google_client.post("/auth/me/google", json=link, headers=csrf(session))
    unlink(google_client, session)
    again = google_client.post("/auth/me/google", json=link, headers=csrf(session))
    assert again.status_code == 200 and again.json()["google_linked"] is True


def test_the_account_always_keeps_a_usable_primary_method(google_client):
    """Password-only, Google-only and both: every route leaves at least one of password/Google."""
    session = google_login(google_client).json()  # Google only
    grant_fresh(google_client)
    assert google_client.request("DELETE", "/auth/me/google", headers=csrf(session)).status_code == 409
    me = google_client.get("/auth/me").json()
    assert me["google_linked"] and not me["has_password"]
    google_client.cookies.clear()
    pw_session = register(google_client)  # password only: nothing to unlink
    assert unlink(google_client, pw_session).status_code == 409
    me = google_client.get("/auth/me").json()
    assert me["has_password"] and not me["google_linked"]
