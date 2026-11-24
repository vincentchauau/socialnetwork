import sys
import types

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from api.werewolf.db import Base, make_engine
from api.werewolf.account_events import DELETED_USER_ID, on_user_deleted, on_user_renamed
from api.werewolf.rolecode import role_code, role_parts
from api.werewolf.models import FINISHED, Game, ids_text
from tests.werewolf.conftest import make_client


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        for room, players in (
            ("r1", [(1, "alice", "WOLF"), (2, "bob", "VILLAGER")]),
            ("r2", [(1, "alice", "VILLAGER"), (3, "carol", "VILLAGER")]),
            ("r3", [(2, "bob", "WOLF"), (3, "carol", "VILLAGER")]),
        ):
            entries = [
                {"user_id": uid, "role": role_code(role, "NONE"), "outcome": "won", "survived": True, "days_survived": 2}
                for uid, name, role in players
            ]
            session.add(Game(room_code=room, status=FINISHED, winner="VILLAGER", days=2, size=6, players=entries,
                             player_ids=ids_text(entry["user_id"] for entry in entries)))
        session.commit()
        yield session


def players(db):
    return [(p["user_id"], role_parts(p["role"])[0]) for game in db.scalars(select(Game).order_by(Game.id)) for p in game.players]


def test_delete_anonymizes_only_that_users_rows_and_keeps_results(db):
    on_user_deleted(db, 1)
    assert players(db) == [
        (DELETED_USER_ID, "WOLF"),
        (2, "VILLAGER"),
        (DELETED_USER_ID, "VILLAGER"),
        (3, "VILLAGER"),
        (2, "WOLF"),
        (3, "VILLAGER"),
    ]
    assert len(db.scalars(select(Game)).all()) == 3
    assert [game.player_ids for game in db.scalars(select(Game).order_by(Game.id))] == ["|2|", "|3|", "|2|3|"]  # found by who is in them (a deleted person is nobody to find)


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


def test_delete_keeps_the_game_facts_and_only_anonymizes_identity(db):
    on_user_deleted(db, 1)
    rows = [p for game in db.scalars(select(Game)) for p in game.players if p["user_id"] == DELETED_USER_ID]
    assert len(rows) == 2 and all(r["outcome"] == "won" and r["days_survived"] == 2 and role_parts(r["role"])[1] == "NONE" for r in rows)


def test_bogus_ids_are_never_treated_as_users(db):
    """Bots have no user id and are never stored; a negative or zero id must not touch anything."""
    before = players(db)
    on_user_deleted(db, -1)
    on_user_renamed(db, -1, "bot")
    on_user_renamed(db, 0, "tombstone")
    assert players(db) == before


def test_rename_changes_nothing_because_no_name_is_stored(db):
    before = players(db)
    on_user_renamed(db, 3, "carla")
    on_user_renamed(db, 99, "nobody")
    assert players(db) == before


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
    with make_client("sqlite://"):
        assert [name for name, _ in calls] == ["werewolf"]  # the game has its own consumer
        assert not handle.stopped
    assert handle.stopped


def test_consumer_not_started_without_redis_or_when_testing(monkeypatch):
    calls = []
    _fake_events(monkeypatch, calls, _Handle())
    monkeypatch.delenv("REDIS_URL", raising=False)
    with make_client("sqlite://"):
        pass
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("TESTING", "1")
    with make_client("sqlite://"):
        pass
    assert calls == []


def test_missing_events_library_is_tolerated(monkeypatch):
    monkeypatch.setitem(sys.modules, "sn_shared.events", None)  # import raises ImportError
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with make_client("sqlite://") as client:
        assert client.get("/health").status_code == 200


def test_handle_without_stop_method_is_tolerated(monkeypatch):
    _fake_events(monkeypatch, [], object())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with make_client("sqlite://"):
        pass
