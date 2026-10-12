import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import DELETED_USER_ID, DELETED_USERNAME, on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import Message


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all(
            [
                Message(room="general", user_id=1, username="alice", content="hi"),
                Message(room="general", user_id=2, username="bob", content="yo"),
                Message(room="other", user_id=1, username="alice", content="again"),
            ]
        )
        session.commit()
        yield session


def rows(db):
    return [(m.user_id, m.username, m.content) for m in db.scalars(select(Message).order_by(Message.id))]


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


def test_rename_updates_all_rooms_for_that_user_only(db):
    on_user_renamed(db, 1, "alicia")
    assert rows(db) == [(1, "alicia", "hi"), (2, "bob", "yo"), (1, "alicia", "again")]


def test_rename_is_idempotent_and_safe_without_data(db):
    on_user_renamed(db, 1, "alicia")
    on_user_renamed(db, 1, "alicia")
    on_user_renamed(db, 99, "nobody")
    assert rows(db) == [(1, "alicia", "hi"), (2, "bob", "yo"), (1, "alicia", "again")]


class _Handle:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _fake_events(monkeypatch, calls: list, handle: _Handle):
    module = types.ModuleType("sn_shared.events")

    def start_account_consumer(app_name, session_factory):
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
