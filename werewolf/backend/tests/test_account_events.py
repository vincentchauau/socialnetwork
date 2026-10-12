import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import DELETED_USER_ID, DELETED_USERNAME, on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import GamePlayer, GameResult


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        for room, players in (
            ("r1", [(1, "alice", "wolf"), (2, "bob", "villager")]),
            ("r2", [(1, "alice", "seer"), (3, "carol", "villager")]),
            ("r3", [(2, "bob", "wolf"), (3, "carol", "villager")]),
        ):
            result = GameResult(room_id=room, winner="village", days=2)
            result.players = [
                GamePlayer(user_id=uid, username=name, role=role, survived=True)
                for uid, name, role in players
            ]
            session.add(result)
        session.commit()
        yield session


def players(db):
    return [(p.user_id, p.username, p.role) for p in db.scalars(select(GamePlayer).order_by(GamePlayer.id))]


def test_delete_anonymizes_only_that_users_rows_and_keeps_results(db):
    on_user_deleted(db, 1)
    assert players(db) == [
        (DELETED_USER_ID, DELETED_USERNAME, "wolf"),
        (2, "bob", "villager"),
        (DELETED_USER_ID, DELETED_USERNAME, "seer"),
        (3, "carol", "villager"),
        (2, "bob", "wolf"),
        (3, "carol", "villager"),
    ]
    assert len(db.scalars(select(GameResult)).all()) == 3


def test_delete_is_idempotent(db):
    on_user_deleted(db, 1)
    first = players(db)
    on_user_deleted(db, 1)
    assert players(db) == first


def test_delete_user_without_data_and_tombstone_id_change_nothing(db):
    before = players(db)
    on_user_deleted(db, 99)
    on_user_deleted(db, DELETED_USER_ID)
    on_user_renamed(db, DELETED_USER_ID, "ghost")
    assert players(db) == before


def test_rename_updates_every_game_of_that_user_only(db):
    on_user_renamed(db, 3, "carla")
    assert [(u, n) for u, n, _ in players(db)] == [
        (1, "alice"), (2, "bob"), (1, "alice"), (3, "carla"), (2, "bob"), (3, "carla"),
    ]


def test_rename_is_idempotent_and_safe_without_data(db):
    on_user_renamed(db, 3, "carla")
    first = players(db)
    on_user_renamed(db, 3, "carla")
    on_user_renamed(db, 99, "nobody")
    assert players(db) == first


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
        assert [name for name, _ in calls] == ["werewolf"]
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
