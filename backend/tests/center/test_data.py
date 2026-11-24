"""/data on center: a person's own non-sensitive profile row, and their own sessions and passkeys (read + delete)."""

from sqlalchemy import select

from api.center.models import Passkey, RecoveryCode, User, UserSession
from tests.center.helpers import CREDS, register

SENSITIVE = {
    "password_hash", "google_sub", "token_version", "totp_enabled", "totp_secret", "totp_pending_secret",
    "totp_last_step", "audio_embedding", "face_embedding", "voice_login", "webcam_login", "biometric_2fa",
    "group", "phone", "kind",
}  # fmt: skip


def seed_bob(client) -> int:
    """A second person with a session and a passkey, written straight to the database."""
    with client.app.state.session_factory() as db:
        bob = User(username="Bob", password_hash="x", email="bob@example.com")
        db.add(bob)
        db.flush()
        db.add(UserSession(sid="b" * 32, user_id=bob.id, method="password"))
        db.add(Passkey(user_id=bob.id, credential_id=b"cred-bob", public_key=b"pk", user_handle=b"h"))
        db.add(RecoveryCode(user_id=bob.id, code_hash="h"))
        db.commit()
        return bob.id


def my_id(client) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(User.id).where(User.username == CREDS["username"]))


def test_anonymous_is_401(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/users").status_code == 401


def test_tables_and_ops(client):
    register(client)
    tables = {t["name"]: t for t in client.get("/records/tables").json()}
    assert tables == {}  # the sessions and passkeys are for admins; the people use the account routes
    for name in ("recovery_codes", "verification_codes", "qr_logins", "reserved_usernames", "account_events"):
        assert client.get(f"/records/{name}").status_code == 404


def test_users_shows_only_my_own_public_row(client):
    register(client)
    bob = seed_bob(client)
    assert client.get("/records/users").status_code == 404  # the accounts are for admins; a person reads their profile on /center
    assert client.get(f"/records/users/{bob}").status_code == 404
    assert client.post("/records/users", json={"values": {}}).status_code == 404
    assert client.patch(f"/records/users/{bob}", json={"values": {"name": "x"}}).status_code == 404
    assert client.delete(f"/records/users/{bob}").status_code == 404


def test_sessions_are_mine_and_deleting_revokes(client, revocations):
    register(client)
    seed_bob(client)
    assert client.get("/records/user_sessions").status_code == 404  # the sessions are for admins; a person signs out on /center
    assert client.delete(f"/records/user_sessions/{'b' * 32}").status_code == 404
    assert client.post("/records/user_sessions", json={"values": {}}).status_code == 404


def test_passkeys_are_mine_with_secrets_masked(client):
    register(client)
    bob = seed_bob(client)
    with client.app.state.session_factory() as db:
        db.add(Passkey(user_id=my_id(client), credential_id=b"cred-me", public_key=b"pk", user_handle=b"h"))
        db.commit()
    assert client.get("/records/passkeys").status_code == 404  # the passkeys are for admins; a person manages them in the app
    with client.app.state.session_factory() as db:
        bobs = db.scalar(select(Passkey.id).where(Passkey.user_id == bob))
    assert client.get(f"/records/passkeys/{bobs}").status_code == 404
    assert client.delete(f"/records/passkeys/{bobs}").status_code == 404
    assert client.patch(f"/records/passkeys/{bobs}", json={"values": {}}).status_code == 404
