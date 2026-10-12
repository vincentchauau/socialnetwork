import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import Comment, Like, Photo
from app.storage import PhotoStorage


@pytest.fixture
def storage(tmp_path):
    return PhotoStorage(tmp_path / "uploads")


def stored_names(stem: str) -> tuple[str, str]:
    padded = stem.rjust(32, "0")
    return f"{padded}.png", f"{padded}_thumb.webp"


def add_photo(session, storage, user_id, username, stem):
    image, thumb = stored_names(stem)
    for name in (image, thumb):
        (storage._root / name).write_bytes(b"x")
    photo = Photo(
        user_id=user_id, username=username, image_name=image, thumb_name=thumb,
        content_type="image/png", thumb_content_type="image/webp", width=1, height=1,
    )
    session.add(photo)
    session.flush()
    return photo


@pytest.fixture
def db(storage):
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        a1 = add_photo(session, storage, 1, "alice", "a1")
        a2 = add_photo(session, storage, 1, "alice", "a2")
        b1 = add_photo(session, storage, 2, "bob", "b1")
        session.add_all(
            [
                Like(photo_id=a1.id, user_id=2),  # bob likes alice's photo
                Like(photo_id=b1.id, user_id=1),  # alice likes bob's photo
                Like(photo_id=b1.id, user_id=3),
                Comment(photo_id=a2.id, user_id=2, username="bob", content="nice"),
                Comment(photo_id=b1.id, user_id=1, username="alice", content="cool"),
                Comment(photo_id=b1.id, user_id=3, username="carol", content="wow"),
            ]
        )
        session.commit()
        yield session


def files(storage):
    return sorted(p.name for p in storage._root.iterdir())


def state(db):
    return {
        "photos": [(p.user_id, p.username) for p in db.scalars(select(Photo).order_by(Photo.id))],
        "likes": [(x.photo_id, x.user_id) for x in db.scalars(select(Like).order_by(Like.id))],
        "comments": [(c.user_id, c.username) for c in db.scalars(select(Comment).order_by(Comment.id))],
    }


def test_delete_removes_own_content_files_and_foreign_reactions_to_it(db, storage):
    on_user_deleted(db, 1)
    db.commit()
    assert state(db) == {
        "photos": [(2, "bob")],
        "likes": [(3, 3)],
        "comments": [(3, "carol")],
    }
    assert files(storage) == sorted(stored_names("b1"))


def test_delete_is_idempotent(db):
    on_user_deleted(db, 1)
    first = state(db)
    on_user_deleted(db, 1)
    assert state(db) == first


def test_delete_tolerates_already_missing_files(db, storage):
    for path in storage._root.iterdir():
        path.unlink()
    on_user_deleted(db, 1)
    assert [p[0] for p in state(db)["photos"]] == [2]


def test_delete_user_without_data_changes_nothing(db, storage):
    before, before_files = state(db), files(storage)
    on_user_deleted(db, 99)
    assert state(db) == before
    assert files(storage) == before_files


def test_rename_updates_photos_and_comments_only_for_that_user(db):
    on_user_renamed(db, 1, "alicia")
    assert state(db)["photos"] == [(1, "alicia"), (1, "alicia"), (2, "bob")]
    assert state(db)["comments"] == [(2, "bob"), (1, "alicia"), (3, "carol")]


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
        assert [name for name, _ in calls] == ["photos"]
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
