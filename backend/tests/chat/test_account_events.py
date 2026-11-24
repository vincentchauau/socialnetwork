import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sn_shared import directory
from api.chat.social import models as social_models
from sqlalchemy.orm import sessionmaker

from api.chat import service
from api.chat.account_events import DELETED_USER_ID, DELETED_USERNAME, on_user_deleted, on_user_renamed
from api.chat.db import Base, make_engine
from api.chat.main import create_app
from api.chat.models import Message


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    social_models.ensure_tables(engine)  # the people side goes with the account too
    directory.ensure_table_for_sqlite(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all(
            [
                directory.Person(user_id=1, username="alice"),
                directory.Person(user_id=2, username="bob"),
                Message(room_id=101, user_id=1, content="hi"),
                Message(room_id=101, user_id=2, content="yo"),
                Message(room_id=102, user_id=1, content="again"),
            ]
        )
        session.commit()
        yield session


def rows(db):
    messages = db.scalars(select(Message).order_by(Message.id)).all()
    return [(m.user_id, m.username, m.content) for m in service.show(db, messages)]


def test_deleted_user_messages_are_anonymized_and_kept(db):
    on_user_deleted(db, 1)
    assert rows(db) == [
        (DELETED_USER_ID, DELETED_USERNAME, "hi"),
        (2, "bob", "yo"),
        (DELETED_USER_ID, DELETED_USERNAME, "again"),
    ]


def test_delete_is_idempotent(db):
    on_user_deleted(db, 1)
    first = rows(db)
    on_user_deleted(db, 1)
    assert rows(db) == first


def test_delete_user_without_data_changes_nothing(db):
    before = rows(db)
    on_user_deleted(db, 99)
    assert rows(db) == before


def test_tombstone_id_is_never_matched(db):
    on_user_deleted(db, 1)
    on_user_deleted(db, DELETED_USER_ID)
    on_user_renamed(db, DELETED_USER_ID, "ghost")
    assert rows(db)[0] == (DELETED_USER_ID, DELETED_USERNAME, "hi")


def test_a_rename_is_seen_at_once_because_the_name_is_read_from_users(db):
    db.get(directory.Person, 1).username = "alicia"
    db.flush()
    on_user_renamed(db, 1, "alicia")  # nothing to do here
    assert rows(db) == [(1, "alicia", "hi"), (2, "bob", "yo"), (1, "alicia", "again")]


def test_rename_is_idempotent_and_safe_without_data(db):
    before = rows(db)
    on_user_renamed(db, 1, "alicia")
    on_user_renamed(db, 1, "alicia")
    on_user_renamed(db, 99, "nobody")
    assert rows(db) == before


class _Handle:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _fake_events(monkeypatch, calls: list, handle: _Handle):
    module = types.ModuleType("sn_shared.events")

    def start_account_consumer(app_name, session_factory, **_):
        calls.append((app_name, session_factory))
        return handle

    module.start_account_consumer = start_account_consumer
    monkeypatch.setitem(sys.modules, "sn_shared.events", module)


def test_consumer_starts_and_stops_with_lifespan(monkeypatch):
    calls, handle = [], _Handle()
    _fake_events(monkeypatch, calls, handle)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(create_app("sqlite://")):
        assert [name for name, _ in calls] == ["chat"]
        assert not handle.stopped
    assert handle.stopped


def test_consumer_not_started_without_redis_or_when_testing(monkeypatch):
    calls = []
    _fake_events(monkeypatch, calls, _Handle())
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(create_app("sqlite://")):
        pass
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("TESTING", "1")
    with TestClient(create_app("sqlite://")):
        pass
    assert calls == []


def test_missing_events_library_is_tolerated(monkeypatch):
    monkeypatch.setitem(sys.modules, "sn_shared.events", None)  # import raises ImportError
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(create_app("sqlite://")) as client:
        assert client.get("/health").status_code == 200


def test_handle_without_stop_method_is_tolerated(monkeypatch):
    _fake_events(monkeypatch, [], object())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(create_app("sqlite://")):
        pass


# ---- rooms and memberships ----------------------------------------------------------------------------------------


from api.chat.models import Room, RoomMember  # noqa: E402


def make_room(db, slug, owner, members=(), kind="chat"):
    room = Room(slug=slug, title=slug, user_id=owner, kind=kind)
    db.add(room)
    db.flush()
    db.add(RoomMember(room_id=room.id, user_id=owner))
    for user_id in members:
        db.add(RoomMember(room_id=room.id, user_id=user_id))
    db.flush()
    return room


def test_a_deleted_owner_hands_the_room_to_the_member_with_the_lowest_id(db):
    room = make_room(db, "talk", owner=1, members=(5, 7, 6))
    on_user_deleted(db, 1)
    db.flush()
    db.refresh(room)
    assert room.user_id == 5
    members = {m.user_id: m for m in db.scalars(select(RoomMember).where(RoomMember.room_id == room.id))}
    assert {u: service.role_of(room, m) for u, m in members.items()} == {1: "member", 5: "owner", 7: "member", 6: "member"}
    assert members[1].status == "left"  # the row stays


def test_a_room_left_with_nobody_is_closed_and_keeps_its_messages(db):
    room = make_room(db, "solo", owner=1)
    db.add(Message(room_id=room.id, user_id=1, content="alone"))
    db.flush()
    on_user_deleted(db, 1)
    db.flush()
    db.refresh(room)
    assert room.state == "closed"
    kept = db.scalars(select(Message).where(Message.room_id == room.id)).all()
    assert [(m.content, m.user_id, m.username) for m in service.show(db, kept)] == [("alone", 0, "Người dùng đã xóa")]


def test_a_direct_chat_ends_when_either_person_goes(db):
    mine = make_room(db, "dm-1-2", owner=1, members=(2,), kind="dm")
    theirs = make_room(db, "dm-2-3", owner=3, members=(2,), kind="dm")
    on_user_deleted(db, 2)
    db.flush()
    db.refresh(mine)
    db.refresh(theirs)
    assert mine.state == "closed" and theirs.state == "closed"


def test_memberships_become_left_and_a_rename_changes_nothing(db):
    room = make_room(db, "talk", owner=1, members=(2,))
    db.add(Message(room_id=room.id, user_id=2, content="yo"))
    db.flush()
    on_user_renamed(db, 2, "robert")
    db.flush()
    on_user_deleted(db, 2)
    db.flush()
    gone = db.get(RoomMember, (room.id, 2))
    assert gone is not None and gone.status == "left"
    on_user_deleted(db, 2)  # idempotent
    db.flush()
    assert db.get(RoomMember, (room.id, 2)).status == "left"
    on_user_renamed(db, 0, "x")


def test_the_name_in_system_lines_is_scrubbed_with_the_name_the_event_carries(db):
    """Center has removed the row of `users` before the handler runs: the event brings the old name."""
    db.add_all([Message(room_id=101, user_id=-1, content="kicked:bob"), RoomMember(room_id=101, user_id=2, status="joined")])
    db.commit()
    db.delete(db.get(directory.Person, 2))
    db.commit()
    on_user_deleted(db, 2, old_username="bob")
    assert db.scalars(select(Message.content).where(Message.kind == "system")).all() == [f"kicked:{DELETED_USERNAME}"]
