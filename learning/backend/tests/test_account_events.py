import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import DELETED_USER_ID, DELETED_USERNAME, on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import Course, Enrollment, Lesson, LessonCompletion, Quiz, QuizAttempt


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        alice_course = Course(owner_id=1, owner_username="alice", title="A", level="beginner", published=True)
        bob_course = Course(owner_id=2, owner_username="bob", title="B", level="beginner", published=True)
        session.add_all([alice_course, bob_course])
        session.flush()
        alice_lesson = Lesson(course_id=alice_course.id, title="l", position=1)
        bob_lesson = Lesson(course_id=bob_course.id, title="l", position=1)
        session.add_all([alice_lesson, bob_lesson])
        session.flush()
        alice_quiz = Quiz(lesson_id=alice_lesson.id, title="q", pass_percent=50)
        bob_quiz = Quiz(lesson_id=bob_lesson.id, title="q", pass_percent=50)
        session.add_all([alice_quiz, bob_quiz])
        session.flush()
        session.add_all(
            [
                Enrollment(course_id=alice_course.id, user_id=2, username="bob"),
                Enrollment(course_id=alice_course.id, user_id=3, username="carol", certificate_code="C1"),
                Enrollment(course_id=bob_course.id, user_id=1, username="alice", certificate_code="C2"),
                LessonCompletion(lesson_id=alice_lesson.id, user_id=2),
                LessonCompletion(lesson_id=bob_lesson.id, user_id=1),
                QuizAttempt(quiz_id=alice_quiz.id, user_id=2, score_percent=80, passed=True),
                QuizAttempt(quiz_id=bob_quiz.id, user_id=1, score_percent=10, passed=False),
            ]
        )
        session.commit()
        yield session


def state(db):
    return {
        "courses": [
            (c.owner_id, c.owner_username, c.published) for c in db.scalars(select(Course).order_by(Course.id))
        ],
        "enrollments": [
            (e.user_id, e.username, e.certificate_code)
            for e in db.scalars(select(Enrollment).order_by(Enrollment.id))
        ],
        "completions": [c.user_id for c in db.scalars(select(LessonCompletion).order_by(LessonCompletion.id))],
        "attempts": [a.user_id for a in db.scalars(select(QuizAttempt).order_by(QuizAttempt.id))],
    }


def test_delete_removes_progress_and_anonymizes_authored_courses(db):
    on_user_deleted(db, 1)
    assert state(db) == {
        "courses": [(DELETED_USER_ID, DELETED_USERNAME, True), (2, "bob", True)],
        "enrollments": [(2, "bob", None), (3, "carol", "C1")],
        "completions": [2],
        "attempts": [2],
    }


def test_delete_learner_keeps_courses_and_other_learners(db):
    on_user_deleted(db, 2)
    assert state(db) == {
        "courses": [(1, "alice", True), (DELETED_USER_ID, DELETED_USERNAME, True)],
        "enrollments": [(3, "carol", "C1"), (1, "alice", "C2")],
        "completions": [1],
        "attempts": [1],
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


def test_rename_updates_courses_and_enrollments_for_that_user_only(db):
    on_user_renamed(db, 1, "alicia")
    snap = state(db)
    assert snap["courses"] == [(1, "alicia", True), (2, "bob", True)]
    assert snap["enrollments"] == [(2, "bob", None), (3, "carol", "C1"), (1, "alicia", "C2")]


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
        assert [name for name, _ in calls] == ["learning"]
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
