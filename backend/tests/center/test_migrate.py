import sqlalchemy as sa
from tests.center.helpers import sqlite_indexes
from fastapi.testclient import TestClient

from api.center import models  # noqa: F401  (registers the tables on Base)
from api.center.db import Base, make_engine
from api.center.main import create_app
from api.center.migrate import ensure_columns
from sn_shared import hash_password as bcrypt_hash

NEW_COLUMNS = {
    "email", "google_sub", "group", "kind", "token_version", "audio_embedding", "face_embedding",
    "biometric_2fa", "voice_login", "webcam_login", "email_verified", "email_from_google",
    "totp_enabled", "totp_secret", "totp_pending_secret", "totp_last_step", "username_changed_at",
    "phone", "phone_verified", "name", "address",
    "headline", "summary", "birth_date", "city", "region", "country",
    "avatar_url", "links", "experience",
    "education", "skills", "languages", "certifications", "projects", "visibility", "interests", "persona_role", "speaking_style",
}  # fmt: skip


def make_old_db(path, password="legacy-pass-1"):
    """A database exactly as the previous version created it, with one bcrypt user."""
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(32) NOT NULL, "
                "password_hash VARCHAR(100) NOT NULL, created_at DATETIME NOT NULL)"
            )
        )
        conn.execute(sa.text("CREATE UNIQUE INDEX ix_users_username ON users (username)"))
        conn.execute(
            sa.text("INSERT INTO users (username, password_hash, created_at) VALUES ('olduser', :h, '2024-01-01')"),
            {"h": bcrypt_hash(password)},
        )
    engine.dispose()
    return f"sqlite:///{path}"


def test_ensure_columns_adds_every_missing_column(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))

    added = ensure_columns(engine)

    assert set(added) == NEW_COLUMNS
    inspector = sa.inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("users")}
    assert not columns["group"]["nullable"] and not columns["token_version"]["nullable"]
    assert not columns["voice_login"]["nullable"] and columns["email"]["nullable"]
    with engine.connect() as conn:
        row = conn.execute(sa.text('SELECT "group", token_version, voice_login, email FROM users')).one()
    assert tuple(row) == ("user", 0, 0, None)
    unique = {name for name, is_unique in sqlite_indexes(engine, "users").items() if is_unique}
    assert {"uq_users_email", "uq_users_google_sub"} <= unique


def test_ensure_columns_is_idempotent(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))
    ensure_columns(engine)
    assert ensure_columns(engine) == []


def test_ensure_columns_ignores_a_missing_table():
    assert ensure_columns(make_engine("sqlite://")) == []


def test_fresh_database_matches_migrated_one(tmp_path):
    fresh = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    Base.metadata.create_all(fresh)
    migrated = make_engine(make_old_db(tmp_path / "old.db"))
    ensure_columns(migrated)

    def shape(engine):
        inspector = sa.inspect(engine)
        return (
            {c["name"] for c in inspector.get_columns("users")},
            {name for name, is_unique in sqlite_indexes(engine, "users").items() if is_unique} - {"ix_users_username"},
        )

    assert shape(fresh) == shape(migrated)


def test_unique_email_is_enforced_but_nulls_may_repeat(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))
    ensure_columns(engine)
    insert = sa.text("INSERT INTO users (username, password_hash, created_at, email) VALUES (:u, '!', '2024', :e)")
    with engine.begin() as conn:
        conn.execute(insert, {"u": "n1", "e": None})
        conn.execute(insert, {"u": "n2", "e": None})
        conn.execute(insert, {"u": "e1", "e": "a@example.com"})
    try:
        with engine.begin() as conn:
            conn.execute(insert, {"u": "e2", "e": "a@example.com"})
    except sa.exc.IntegrityError:
        return
    raise AssertionError("duplicate email was accepted")


def test_app_upgrades_old_database_and_legacy_user_can_log_in_and_is_rehashed(tmp_path):
    url = make_old_db(tmp_path / "old.db", password="legacy-pass-1")
    app = create_app(url)  # runs ensure_columns
    with TestClient(app) as client:
        response = client.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"})
        assert response.status_code == 200
        assert response.json()["group"] == "user"
        assert client.get("/auth/me").json()["has_password"] is True
        assert client.post("/auth/login", json={"username": "olduser", "password": "nope-nope-1"}).status_code == 401

    with app.state.session_factory() as db:
        stored = db.execute(sa.text("SELECT password_hash FROM users")).scalar_one()
    assert stored.startswith("scrypt$")  # transparently upgraded from bcrypt
    with TestClient(app) as client:  # and the new hash works
        assert client.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"}).status_code == 200


def test_biometric_2fa_column_is_added_off_by_default_to_existing_rows(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))

    assert "biometric_2fa" in ensure_columns(engine)

    columns = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}
    assert not columns["biometric_2fa"]["nullable"]
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT biometric_2fa FROM users")).scalar_one() == 0
    assert "biometric_2fa" not in ensure_columns(engine)


def test_database_missing_only_biometric_2fa_gets_just_that_column(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))
    ensure_columns(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE users DROP COLUMN biometric_2fa"))
    assert ensure_columns(engine) == ["biometric_2fa"]


def _flags(engine):
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT username, voice_login, webcam_login FROM users")).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def test_new_method_columns_are_added_off_by_default(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))
    added = ensure_columns(engine)
    assert {"voice_login", "webcam_login"} <= set(added)
    columns = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}
    assert not columns["voice_login"]["nullable"] and not columns["webcam_login"]["nullable"]
    assert _flags(engine) == {"olduser": (0, 0)}


def _legacy_code_tables(engine):
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO users (id, username, password_hash, created_at) VALUES (7, 'ann', '!', '2024')"))
        conn.execute(sa.text(
            "CREATE TABLE email_tokens (id INTEGER PRIMARY KEY, user_id INTEGER, purpose VARCHAR(16), email VARCHAR(254), "
            "token_hash VARCHAR(64), code_hash VARCHAR(64), expires_at DATETIME, used_at DATETIME, attempts INTEGER, created_at DATETIME)"))
        conn.execute(sa.text(
            "CREATE TABLE phone_codes (id INTEGER PRIMARY KEY, user_id INTEGER, purpose VARCHAR(16), phone VARCHAR(16), "
            "code_hash VARCHAR(64), attempts INTEGER, expires_at DATETIME, used_at DATETIME, created_at DATETIME)"))
        conn.execute(sa.text("INSERT INTO email_tokens VALUES (5, 7, 'verify', 'a@b.co', 'tok', 'cod', '2099-01-01', NULL, 2, '2024')"))
        conn.execute(sa.text("INSERT INTO phone_codes VALUES (5, 7, 'login', '+84900000001', 'pc', 1, '2099-01-01', NULL, '2024')"))


def test_legacy_code_tables_are_copied_once_into_verification_codes(tmp_path):
    engine = make_engine(make_old_db(tmp_path / "old.db"))
    Base.metadata.create_all(engine)
    _legacy_code_tables(engine)

    ensure_columns(engine)

    query = "SELECT id, user_id, purpose, channel, target, token_hash, code_hash, attempts FROM verification_codes ORDER BY channel"
    with engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(sa.text(query))]
    assert rows[0] == (5, 7, "verify", "email", "a@b.co", "tok", "cod", 2)  # ids kept: the code MAC is bound to the id
    assert rows[1][1:] == (7, "login", "phone", "+84900000001", None, None, 1) and rows[1][0] != 5
    ensure_columns(engine)  # the table is no longer empty: nothing is copied again
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT COUNT(*) FROM verification_codes")).scalar() == 2
        assert {"email_tokens", "phone_codes"} <= set(sa.inspect(engine).get_table_names())  # left for the owner to drop


def test_old_database_gets_the_event_and_reservation_tables_and_can_rename(tmp_path):
    url = make_old_db(tmp_path / "old.db", password="legacy-pass-1")
    with TestClient(create_app(url)) as client:
        assert {"account_events", "reserved_usernames"} <= set(sa.inspect(make_engine(url)).get_table_names())
        session = client.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"}).json()
        response = client.post(
            "/auth/me/username", json={"username": "newuser", "password": "legacy-pass-1"},
            headers={"X-CSRF-Token": session["csrf_token"]},
        )
        assert response.status_code == 200 and response.json()["username"] == "newuser"
