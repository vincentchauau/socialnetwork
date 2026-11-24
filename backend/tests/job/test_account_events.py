import sys
import types

import pytest
from fastapi.testclient import TestClient
from sn_shared import comments, directory
from sn_shared.directory import DELETED_USERNAME
from sn_shared.testing import add_person
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from api.job.account_events import DELETED_USER_ID, on_user_deleted, on_user_renamed
from api.job.db import Base, make_engine
from api.job.main import create_app
from api.job.models import JobApplicant, JobDescription


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    comments.ensure_table(engine)
    directory.ensure_table_for_sqlite(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        alice_job = JobDescription(owner_id=1, title="A", company="X", employment_type="full_time")
        bob_job = JobDescription(owner_id=2, title="B", company="Y", employment_type="full_time")
        session.add_all([alice_job, bob_job])
        session.flush()
        session.add_all(
            [
                JobApplicant(job_description_id=alice_job.id, user_id=2, status="submitted", saved=True),
                JobApplicant(job_description_id=alice_job.id, user_id=3, status="submitted"),
                JobApplicant(
                    job_description_id=bob_job.id, user_id=1, status="submitted", contact_email="a@x.io", saved=True
                ),
            ]
        )
        session.commit()
        yield session


def state(db):
    return {
        "jobs": [
            (j.owner_id, j.status) for j in db.scalars(select(JobDescription).order_by(JobDescription.id))
        ],
        "applicants": [a.user_id for a in db.scalars(select(JobApplicant).order_by(JobApplicant.id))],
    }


def test_delete_removes_personal_data_and_anonymizes_and_closes_jobs(db):
    on_user_deleted(db, 1)
    assert state(db) == {
        "jobs": [(DELETED_USER_ID, "closed"), (2, "open")],
        "applicants": [2, 3],  # applicants to alice's job keep their history
    }


def test_delete_applicant_leaves_jobs_and_other_applications(db):
    on_user_deleted(db, 2)
    assert state(db) == {
        "jobs": [(1, "open"), (DELETED_USER_ID, "closed")],
        "applicants": [3, 1],
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


def test_a_rename_is_nothing_to_do_names_follow_the_users_row(db):
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    add_person(factory, 1, "alice")
    before = state(db)
    on_user_renamed(db, 1, "alicia")
    assert state(db) == before
    add_person(factory, 1, "alicia")
    assert directory.names(db, [1, DELETED_USER_ID]) == {1: "alicia", DELETED_USER_ID: DELETED_USERNAME}


def test_rename_is_safe_without_data(db):
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
        assert [name for name, _ in calls] == ["job"]
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
