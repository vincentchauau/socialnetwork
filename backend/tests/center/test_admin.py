"""Admin CRUD over center's tables: read + delete only; deleting a user or a session keeps the system consistent."""

from sqlalchemy import select

from api.center.models import AccountEvent, RecoveryCode, ReservedUsername, User, UserSession
from api.center.events import USER_DELETED
from sn_shared import COOKIE_NAME, create_token
from tests.center.helpers import CREDS, register

ADMIN_ID = 9000
ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(ADMIN_ID, 'root', group='admin')}"}
TABLES = {
    "users", "user_sessions", "passkeys", "recovery_codes", "verification_codes",
    "qr_logins", "reserved_usernames", "account_events",
}  # fmt: skip


def user_id_of(client, username: str) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(User.id).where(User.username == username))


def test_admin_requires_admin_role(client):
    register(client)
    client.cookies.clear()
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers={"Cookie": client.headers.get("Cookie", "")}).status_code in (401, 403)
    assert client.get("/records/users").status_code == 401


def test_all_tables_read_delete_only_with_secrets_masked(client):
    register(client)
    tables = {t["name"]: t for t in client.get("/records/tables", headers=ADMIN).json()}
    assert set(tables) == TABLES
    assert all(t["writable"] is True for t in tables.values())
    secret = lambda name: {c["name"] for c in tables[name]["columns"] if c["secret"]}  # noqa: E731
    assert {"password_hash", "totp_secret", "audio_embedding", "face_embedding"} <= secret("users")
    assert {"credential_id", "public_key", "user_handle"} <= secret("passkeys")
    row = client.get("/records/users", headers=ADMIN).json()["rows"][0]
    assert row["password_hash"] == "***" and row["username"] == CREDS["username"]
    assert client.post("/records/users", json={"values": {}}, headers=ADMIN).status_code == 422  # the admin may create; the values are checked
    assert client.patch(f"/records/users/{row['id']}", json={"values": {"group": "admin"}}, headers=ADMIN).status_code == 200  # the admin changes any row


def test_deleting_a_user_runs_the_account_deletion_path(client, revocations):
    register(client)
    uid = user_id_of(client, CREDS["username"])
    assert client.delete(f"/records/users/{uid}", headers=ADMIN).status_code == 204
    with client.app.state.session_factory() as db:
        assert db.get(User, uid) is None
        event = db.scalar(select(AccountEvent).where(AccountEvent.user_id == uid))
        assert event is not None and event.type == USER_DELETED and CREDS["username"] in event.payload
        assert db.scalar(select(ReservedUsername).where(ReservedUsername.user_id == uid)) is not None
        assert db.scalar(select(UserSession).where(UserSession.user_id == uid)) is None
    assert int(revocations.get(f"sn:minver:{uid}")) >= 1  # the other apps reject its tokens


def test_admin_cannot_delete_own_account(client):
    register(client)
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        user.group = "admin"
        uid = user.id
        db.commit()
    own = {"Cookie": f"{COOKIE_NAME}={create_token(uid, CREDS['username'], group='admin')}"}
    assert client.delete(f"/records/users/{uid}", headers=own).status_code == 409
    with client.app.state.session_factory() as db:
        assert db.get(User, uid) is not None
        assert db.scalar(select(AccountEvent)) is None


def test_deleting_a_session_publishes_its_revocation(client, revocations):
    register(client)
    with client.app.state.session_factory() as db:
        sid = db.scalar(select(UserSession.sid))
    assert client.delete(f"/records/user_sessions/{sid}", headers=ADMIN).status_code == 204
    assert revocations.exists(f"sn:revoked:sid:{sid}") == 1
    with client.app.state.session_factory() as db:
        assert db.get(UserSession, sid) is None


def test_other_tables_delete_plainly(client):
    register(client)
    uid = user_id_of(client, CREDS["username"])
    with client.app.state.session_factory() as db:
        db.add(RecoveryCode(user_id=uid, code_hash="x" * 64))
        db.commit()
        code_id = db.scalar(select(RecoveryCode.id))
    assert client.get(f"/records/recovery_codes/{code_id}", headers=ADMIN).json()["code_hash"] == "***"
    assert client.delete(f"/records/recovery_codes/{code_id}", headers=ADMIN).status_code == 204
    assert client.get("/records/passkeys", headers=ADMIN).json()["total"] == 0
