"""Usernames keep the typed capitalisation; uniqueness, lookups, reservations and throttles ignore case."""

import json

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import usernames
from app.handles import key_of
from app.migrate import ensure_columns
from app.models import AccountEvent, User
from sn_shared import COOKIE_NAME, decode_token
from tests.helpers import CREDS, STRONG, register
from tests.test_migrate import make_old_db
from tests.test_rename import events, rename, reservations

PW = CREDS["password"]


def test_register_keeps_the_typed_capitalisation_everywhere(client):
    session = register(client)
    assert session["username"] == "Alice"
    assert client.get("/auth/me").json()["username"] == "Alice"
    assert decode_token(client.cookies.get(COOKIE_NAME)).username == "Alice"
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert (user.username, user.username_key) == ("Alice", "alice")


def test_register_strips_and_keeps_case_for_dots_and_dashes(client):
    response = client.post("/auth/register", json={**CREDS, "username": "  Al.ice-1_x "})
    assert response.json()["username"] == "Al.ice-1_x"


@pytest.mark.parametrize("name", ["alice", "ALICE", "aLiCe"])
def test_login_ignores_capitalisation(client, name):
    register(client)
    client.cookies.clear()
    response = client.post("/auth/login", json={"username": name, "password": PW})
    assert response.status_code == 200 and response.json()["username"] == "Alice"


@pytest.mark.parametrize("name", ["alice", "ALICE", "Alice"])
def test_names_differing_only_by_case_cannot_register(client, name):
    register(client)
    response = client.post("/auth/register", json={"username": name, "password": STRONG})
    assert response.status_code == 409 and response.json()["detail"] == "Username already taken"


def test_database_refuses_two_accounts_differing_by_case(client):
    register(client)
    with client.app.state.session_factory() as db:
        db.add(User(username="ALICE", password_hash="!"))
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize("name", ["admin", "Admin", "ADMIN"])
def test_system_names_are_blocked_in_any_case(client, name):
    response = client.post("/auth/register", json={"username": name, "password": STRONG})
    assert response.status_code == 409 and response.json()["detail"] == "Username already taken"


def test_login_throttle_is_keyed_by_the_key_not_the_capitalisation(client):
    register(client)
    client.cookies.clear()
    for name in ["alice", "ALICE", "Alice", "aLice", "alICE", "ALice"]:
        assert client.post("/auth/login", json={"username": name, "password": "wrong-pass-1"}).status_code in (401, 429)
    assert client.post("/auth/login", json={"username": "aliCE", "password": PW}).status_code == 429


def test_rename_to_a_capitalisation_variant_is_allowed_once(client):
    session = register(client)
    response = rename(client, session, "ALICE")
    assert response.status_code == 200 and response.json()["username"] == "ALICE"
    assert client.get("/auth/me").json()["username"] == "ALICE"
    assert rename(client, response.json(), "alice").status_code == 409  # one rename per 30 days
    with client.app.state.session_factory() as db:
        assert db.scalar(select(User.username_key)) == "alice"


def test_rename_to_the_exact_same_text_is_refused(client):
    session = register(client)
    assert rename(client, session, "Alice").status_code == 422


def test_rename_reserves_the_old_key_and_blocks_any_capitalisation(client):
    session = register(client)
    rename(client, session, "bobby")
    assert set(reservations(client)) == {"alice"}
    client.cookies.clear()
    response = client.post("/auth/register", json={"username": "ALICE", "password": STRONG})
    assert response.status_code == 409
    with client.app.state.session_factory() as db:
        assert usernames.unavailable(db, "aLiCe")


def test_rename_event_carries_the_display_names(client):
    session = register(client)
    rename(client, session, "Bobby")
    payloads = [json.loads(e.payload) for e in events(client) if e.type == "user.renamed"]
    assert [(p["username"], p["old_username"]) for p in payloads] == [("Bobby", "Alice")]


def test_taken_by_another_account_in_any_case_is_409_on_rename(client):
    register(client, {"username": "Carol", "password": STRONG})
    client.cookies.clear()
    session = register(client)
    assert rename(client, session, "cAROL").status_code == 409


def test_key_of_strips_and_lowercases():
    assert key_of("  AbC.d ") == "abc.d"


def test_migration_backfills_the_key_and_adds_the_unique_index(tmp_path):
    engine = sa.create_engine(make_old_db(tmp_path / "old.db"))
    added = ensure_columns(engine)
    assert "username_key" in added
    with engine.begin() as conn:
        assert conn.execute(sa.text("SELECT username, username_key FROM users")).one() == ("olduser", "olduser")
        assert "uq_users_username_key" in {i["name"] for i in sa.inspect(conn).get_indexes("users")}
    assert ensure_columns(engine) == []  # idempotent
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO users (username, username_key, password_hash, created_at) "
                             "VALUES ('OldUser', 'olduser', '!', '2024')"))
