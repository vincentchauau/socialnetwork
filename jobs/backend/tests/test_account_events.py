import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import DELETED_USER_ID, DELETED_USERNAME, on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import Application, Posting, Profile, SavedJob


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        alice_job = Posting(owner_id=1, owner_username="alice", title="A", company="X", employment_type="full_time")
        bob_job = Posting(owner_id=2, owner_username="bob", title="B", company="Y", employment_type="full_time")
        session.add_all([alice_job, bob_job])
        session.flush()
        session.add_all(
            [
                Application(posting_id=alice_job.id, applicant_id=2, applicant_username="bob", resume_text="r"),
                Application(posting_id=alice_job.id, applicant_id=3, applicant_username="carol"),
                Application(
                    posting_id=bob_job.id, applicant_id=1, applicant_username="alice", contact_email="a@x.io"
                ),
                SavedJob(user_id=1, posting_id=bob_job.id),
                SavedJob(user_id=2, posting_id=alice_job.id),
                Profile(user_id=1, username="alice", headline="h"),
                Profile(user_id=2, username="bob", headline="h"),
            ]
        )
        session.commit()
        yield session


def state(db):
    return {
        "postings": [
            (p.owner_id, p.owner_username, p.status) for p in db.scalars(select(Posting).order_by(Posting.id))
        ],
        "applications": [
            (a.applicant_id, a.applicant_username) for a in db.scalars(select(Application).order_by(Application.id))
        ],
        "saved": [s.user_id for s in db.scalars(select(SavedJob).order_by(SavedJob.posting_id))],
        "profiles": [(p.user_id, p.username) for p in db.scalars(select(Profile).order_by(Profile.user_id))],
    }


def test_delete_removes_personal_data_and_anonymizes_and_closes_postings(db):
    on_user_deleted(db, 1)
    assert state(db) == {
        "postings": [(DELETED_USER_ID, DELETED_USERNAME, "closed"), (2, "bob", "open")],
        "applications": [(2, "bob"), (3, "carol")],  # applicants to alice's job keep their history
        "saved": [2],
        "profiles": [(2, "bob")],
    }


def test_delete_applicant_leaves_postings_and_other_applications(db):
    on_user_deleted(db, 2)
    assert state(db) == {
        "postings": [(1, "alice", "open"), (DELETED_USER_ID, DELETED_USERNAME, "closed")],
        "applications": [(3, "carol"), (1, "alice")],
        "saved": [1],
        "profiles": [(1, "alice")],
    }


def test_delete_is_idempotent(db):
    on_user_deleted(db, 1)
    first = state(db)
    on_user_deleted(db, 1)
    assert state(db) == first


def test_delete_user_without_data_changes_nothing(db):
    before = state(db)
    on_user_deleted(db, 99)
    on_user_deleted(db, DELETED_USER_ID)
    on_user_renamed(db, DELETED_USER_ID, "ghost")
    assert state(db) == before


def test_rename_updates_every_denormalized_column(db):
    on_user_renamed(db, 1, "alicia")
    snap = state(db)
    assert snap["postings"] == [(1, "alicia", "open"), (2, "bob", "open")]
    assert snap["applications"] == [(2, "bob"), (3, "carol"), (1, "alicia")]
    assert snap["profiles"] == [(1, "alicia"), (2, "bob")]


def test_rename_is_idempotent_and_safe_without_data(db):
    on_user_renamed(db, 1, "alicia")
    first = state(db)
    on_user_renamed(db, 1, "alicia")
    on_user_renamed(db, 99, "nobody")
    assert state(db) == first


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
        assert [name for name, _ in calls] == ["jobs"]
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
