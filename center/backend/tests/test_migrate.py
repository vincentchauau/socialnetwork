import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.db import Base, make_engine
from app.main import create_app
from app.migrate import ensure_columns
from sn_shared import hash_password as bcrypt_hash

NEW_COLUMNS = {
    "email", "google_sub", "role", "token_version", "audio_embedding", "face_embedding", "biometric_login",
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
    assert not columns["role"]["nullable"] and not columns["token_version"]["nullable"]
    assert not columns["biometric_login"]["nullable"] and columns["email"]["nullable"]
    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT role, token_version, biometric_login, email FROM users")).one()
    assert tuple(row) == ("user", 0, 0, None)
    unique = {i["name"] for i in inspector.get_indexes("users") if i["unique"]}
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
            {i["name"] for i in inspector.get_indexes("users") if i["unique"]} - {"ix_users_username"},
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
        assert response.json()["role"] == "user"
        assert client.get("/auth/me").json()["has_password"] is True
        assert client.post("/auth/login", json={"username": "olduser", "password": "nope-nope-1"}).status_code == 401

    with app.state.session_factory() as db:
        stored = db.execute(sa.text("SELECT password_hash FROM users")).scalar_one()
    assert stored.startswith("scrypt$")  # transparently upgraded from bcrypt
    with TestClient(app) as client:  # and the new hash works
        assert client.post("/auth/login", json={"username": "olduser", "password": "legacy-pass-1"}).status_code == 200
