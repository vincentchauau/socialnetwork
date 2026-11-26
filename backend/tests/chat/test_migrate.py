import sqlite3
from datetime import datetime

import sqlalchemy as sa
from fastapi.testclient import TestClient

from api.chat.main import create_app
from api.chat.models import Message, Room, RoomMember
from tests.chat.conftest import ALLOWED_ORIGIN, auth_cookie

# Python 3.12 deprecates sqlite3's default datetime adapter: register the same text format explicitly.
sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))


OLD_MESSAGES = """
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room VARCHAR(32) NOT NULL,
  user_id INTEGER NOT NULL,
  username VARCHAR(32),
  content TEXT NOT NULL,
  created_at DATETIME NOT NULL
)
"""


def old_database(path):
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(sa.text(OLD_MESSAGES))
        rows = [
            ("general", 1, "alice", "hello"),
            ("general", 2, "bob", "hi"),
            ("general", 1, "alice", "again"),
            ("garage", 3, "carol", "anything?"),
            ("garage", 0, "Người dùng đã xóa", "bye"),
        ]
        for room, user_id, name, content in rows:
            connection.execute(
                sa.text("INSERT INTO messages (room, user_id, username, content, created_at) VALUES (:r, :u, :n, :c, '2026-01-01 00:00:00')"),
                {"r": room, "u": user_id, "n": name, "c": content},
            )
    return engine


def test_an_old_database_gets_its_rooms_members_and_links(tmp_path):
    engine = old_database(tmp_path / "old.db")
    with TestClient(create_app(f"sqlite:///{tmp_path / 'old.db'}")) as client:
        rooms = {r["slug"]: r for r in client.get("/rooms", headers=auth_cookie(9, "zed")).json()}
        assert set(rooms) == {"general", "garage"}
        assert rooms["general"]["members"] == 2 and rooms["general"]["user_id"] == 1  # whoever wrote first made it
        assert rooms["general"]["visibility"] == "public" and rooms["general"]["join_policy"] == "open"
        history = client.get("/rooms/general/messages", headers=auth_cookie(9, "zed")).json()
        assert [m["content"] for m in history] == ["hello", "hi", "again"]
        assert all(m["kind"] == "text" for m in history)
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM messages WHERE room_id IS NULL")).scalar() == 0
        members = [row[0] for row in connection.execute(sa.text("SELECT user_id FROM room_members WHERE room_id = (SELECT id FROM rooms WHERE slug = 'general') ORDER BY user_id")).all()]
        assert members == [1, 2]
        assert connection.execute(sa.text("SELECT user_id FROM rooms WHERE slug = 'general'")).scalar() == 1  # its first writer made it, so it is theirs
        garage = connection.execute(sa.text("SELECT user_id FROM room_members WHERE room_id = (SELECT id FROM rooms WHERE slug = 'garage')")).all()
        assert [row[0] for row in garage] == [3]  # the deleted user (0) is nobody's member


def test_running_the_upgrade_again_changes_nothing(tmp_path):
    old_database(tmp_path / "old.db")
    url = f"sqlite:///{tmp_path / 'old.db'}"
    with TestClient(create_app(url)):
        pass
    with TestClient(create_app(url)) as client:
        assert len(client.get("/rooms", headers=auth_cookie(9, "zed")).json()) == 2
        factory = client.app.state.session_factory
        with factory() as session:
            assert session.query(Room).count() == 2
            assert session.query(RoomMember).count() == 3
            assert session.query(Message).count() == 5


def test_an_upgraded_room_can_be_joined_and_talked_in(tmp_path):
    old_database(tmp_path / "old.db")
    with TestClient(create_app(f"sqlite:///{tmp_path / 'old.db'}")) as client:
        headers = {**auth_cookie(9, "zed"), "Origin": ALLOWED_ORIGIN}
        assert client.post("/rooms/general/join", json={}, headers=headers).status_code == 200
        with client.websocket_connect("/ws/general", headers={**auth_cookie(9, "zed"), "Origin": ALLOWED_ORIGIN}) as socket:
            socket.send_json({"content": "new here"})
            while socket.receive_json().get("type") != "message":
                pass
        latest = client.get("/rooms/general/messages", headers=auth_cookie(9, "zed")).json()[-1]
        assert latest["content"] == "new here" and latest["user_id"] == 9


LEGACY_TABLES = """
CREATE TABLE rooms (
  id INTEGER PRIMARY KEY, slug VARCHAR(64) NOT NULL UNIQUE, kind VARCHAR(8) NOT NULL DEFAULT 'chat', title VARCHAR(80) NOT NULL,
  description VARCHAR(200) NOT NULL DEFAULT '', category VARCHAR(32) NOT NULL DEFAULT '', region VARCHAR(80) NOT NULL DEFAULT '',
  owner_id INTEGER NOT NULL, visibility VARCHAR(8) NOT NULL DEFAULT 'public', join_policy VARCHAR(8) NOT NULL DEFAULT 'open',
  post_policy VARCHAR(10) NOT NULL DEFAULT 'everyone', capacity INTEGER NOT NULL DEFAULT 200, state VARCHAR(8) NOT NULL DEFAULT 'open',
  opens_at DATETIME, closes_at DATETIME, dm_key VARCHAR(80) UNIQUE, settings JSON, created_at DATETIME NOT NULL DEFAULT '2026-01-01 00:00:00',
  closed_at DATETIME, deleted_at DATETIME, created_by INTEGER, last_message_at DATETIME
);
CREATE INDEX ix_rooms_listing ON rooms (kind, visibility, state, category, region);
CREATE INDEX ix_rooms_owner ON rooms (owner_id);
CREATE TABLE room_members (
  room_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role VARCHAR(10) NOT NULL DEFAULT 'member', status VARCHAR(8) NOT NULL DEFAULT 'joined',
  muted_until DATETIME, last_read_message_id BIGINT, joined_at DATETIME NOT NULL DEFAULT '2026-01-01 00:00:00', left_at DATETIME, kicked_at DATETIME,
  status_reason VARCHAR(200) NOT NULL DEFAULT '', notify BOOLEAN NOT NULL DEFAULT 1, hidden_at DATETIME, PRIMARY KEY (room_id, user_id)
);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER, user_id INTEGER NOT NULL, kind VARCHAR(8) NOT NULL DEFAULT 'text', content TEXT NOT NULL,
  reply_to_id INTEGER, pinned_at DATETIME, deleted_at DATETIME, edited_at DATETIME, created_at DATETIME NOT NULL DEFAULT '2026-01-01 00:00:00'
);
"""


def test_the_wider_tables_of_the_version_before_are_folded_into_the_ones_that_stay(tmp_path):
    """The owner is `rooms.user_id` (once `owner_id`), a running mute is the reason `muted`, a card starts with the card prefix; the old columns go."""
    path = tmp_path / "legacy.db"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        for statement in [part for part in LEGACY_TABLES.split(";") if part.strip()]:
            connection.execute(sa.text(statement))
        connection.execute(sa.text("INSERT INTO rooms (id, slug, title, owner_id) VALUES (1, 'club', 'Club', 7)"))
        connection.execute(sa.text(
            "INSERT INTO room_members (room_id, user_id, role, muted_until) VALUES (1, 7, 'owner', NULL), (1, 8, 'member', '2999-01-01 00:00:00'), (1, 9, 'member', '2000-01-01 00:00:00')"
        ))
        connection.execute(sa.text(
            "INSERT INTO messages (room_id, user_id, kind, content) VALUES (1, 7, 'text', 'hello'), (1, -1, 'system', 'joined:<8>'), (1, 8, 'card', '{\"type\":\"detail\"}')"
        ))
    with TestClient(create_app(f"sqlite:///{path}")) as client:
        room = client.get("/rooms/club", headers=auth_cookie(7, "gina")).json()
        assert room["user_id"] == 7 and room["me"]["role"] == "owner"
        members = {m["user_id"]: m for m in client.get("/rooms/club/members", headers=auth_cookie(7, "gina")).json()}
        assert members[8]["muted"] is True and members[9]["muted"] is False and members[8]["status"] == "joined"
        kinds = [m["kind"] for m in client.get("/rooms/club/messages", headers=auth_cookie(7, "gina")).json()]
        assert kinds == ["text", "system", "card"]
    with engine.connect() as connection:
        for table, gone in (("rooms", ("description", "region", "post_policy", "owner_id", "settings", "created_at", "last_message_at")),
                            ("room_members", ("role", "muted_until", "joined_at", "left_at", "kicked_at")), ("messages", ("kind",))):
            have = {row[1] for row in connection.execute(sa.text(f"PRAGMA table_info({table})"))}
            assert not set(gone) & have, (table, set(gone) & have)
    with TestClient(create_app(f"sqlite:///{path}")) as client:  # safe to run again
        assert client.get("/rooms/club", headers=auth_cookie(7, "gina")).json()["user_id"] == 7


def test_an_old_database_gets_statuses_and_columns(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    old_database(tmp_path / "old.db")
    engine = sa.create_engine(url)
    with TestClient(create_app(url)):
        pass
    with engine.begin() as connection:  # a database from before: `active`
        connection.execute(sa.text("UPDATE room_members SET status = 'active'"))
    with TestClient(create_app(url)) as client:
        with client.app.state.session_factory() as session:
            assert {m.status for m in session.query(RoomMember)} == {"joined"}
    with TestClient(create_app(url)) as client:  # safe to run again
        with client.app.state.session_factory() as session:
            assert {m.status for m in session.query(RoomMember)} == {"joined"}
