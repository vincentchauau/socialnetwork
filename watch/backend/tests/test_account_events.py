import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import Video, VideoView, WatchlistItem, WatchProgress


@pytest.fixture
def db(upload_dir):
    upload_dir.mkdir(parents=True)
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        videos = []
        for owner_id, owner, name in ((1, "alice", "a1.mp4"), (1, "alice", "a2.mp4"), (2, "bob", "b1.mp4")):
            (upload_dir / name).write_bytes(b"x")
            video = Video(
                owner_id=owner_id, owner=owner, title=name, file_name=name,
                content_type="video/mp4", size_bytes=1,
            )
            session.add(video)
            videos.append(video)
        session.flush()
        a1, _a2, b1 = videos
        session.add_all(
            [
                WatchProgress(user_id=2, video_id=a1.id, seconds=3),  # bob watching alice's video
                WatchProgress(user_id=1, video_id=b1.id, seconds=5),  # alice watching bob's video
                WatchProgress(user_id=3, video_id=b1.id, seconds=7),
                WatchlistItem(user_id=2, video_id=a1.id),
                WatchlistItem(user_id=1, video_id=b1.id),
                WatchlistItem(user_id=3, video_id=b1.id),
                VideoView(user_id=2, video_id=a1.id),
                VideoView(user_id=1, video_id=b1.id),
                VideoView(user_id=3, video_id=b1.id),
            ]
        )
        session.commit()
        yield session


def state(db):
    def keys(model):
        return sorted((r.user_id, r.video_id) for r in db.scalars(select(model)))

    return {
        "videos": [(v.owner_id, v.owner) for v in db.scalars(select(Video).order_by(Video.id))],
        "progress": keys(WatchProgress),
        "watchlist": keys(WatchlistItem),
        "views": keys(VideoView),
    }


def test_delete_removes_videos_files_and_every_row_tied_to_the_user(db, upload_dir):
    on_user_deleted(db, 1)
    db.commit()
    assert state(db) == {
        "videos": [(2, "bob")],
        "progress": [(3, 3)],
        "watchlist": [(3, 3)],
        "views": [(3, 3)],
    }
    assert sorted(p.name for p in upload_dir.iterdir()) == ["b1.mp4"]


def test_delete_is_idempotent(db):
    on_user_deleted(db, 1)
    first = state(db)
    on_user_deleted(db, 1)
    assert state(db) == first


def test_delete_tolerates_already_missing_files(db, upload_dir):
    for path in upload_dir.iterdir():
        path.unlink()
    on_user_deleted(db, 1)
    assert [v[0] for v in state(db)["videos"]] == [2]


def test_delete_user_without_data_changes_nothing(db, upload_dir):
    before = state(db)
    on_user_deleted(db, 99)
    assert state(db) == before
    assert len(list(upload_dir.iterdir())) == 3


def test_rename_updates_owner_only_for_that_user(db):
    on_user_renamed(db, 1, "alicia")
    assert state(db)["videos"] == [(1, "alicia"), (1, "alicia"), (2, "bob")]


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
        assert [name for name, _ in calls] == ["watch"]
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
