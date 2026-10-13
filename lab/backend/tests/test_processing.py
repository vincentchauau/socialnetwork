import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app import repo
from app.db import Base, make_engine
from app.models import LabEvent
from app.processing import LogRecord, LogWriter, NotificationProcessor, parse_log_value, replay_message

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def body(event_id: int) -> bytes:
    return json.dumps({"id": event_id, "userId": 1, "title": "t", "body": "b"}).encode()


def processor(factory):
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return NotificationProcessor(factory, sleep=sleep, work_time=lambda: 0.5, backoff_base=1.0), sleeps


def status_of(factory, event_id):
    with factory() as db:
        row = db.get(LabEvent, event_id)
        return (row.status, row.attempts, row.processed_at is not None)


def test_success_marks_done(factory):
    event_id = repo.create_notification(factory, 1, "hello", "b")
    worker, sleeps = processor(factory)
    assert asyncio.run(worker.handle(body(event_id))) == "done"
    assert status_of(factory, event_id) == ("done", 1, True)
    assert sleeps == [0.5]


def test_fail_title_retries_with_backoff_then_dies(factory):
    event_id = repo.create_notification(factory, 1, "[fail] boom", "b")
    worker, sleeps = processor(factory)
    assert asyncio.run(worker.handle(body(event_id))) == "dead"
    assert status_of(factory, event_id) == ("dead", 3, True)
    assert sleeps == [0.5, 1.0, 0.5, 2.0, 0.5]  # work, backoff 1, work, backoff 2, work


def test_status_is_retrying_between_attempts(factory):
    event_id = repo.create_notification(factory, 1, "[fail]", "b")
    seen = []

    async def sleep(seconds):
        seen.append(status_of(factory, event_id)[:2])

    worker = NotificationProcessor(factory, sleep=sleep, work_time=lambda: 0, backoff_base=0)
    asyncio.run(worker.handle(body(event_id)))
    assert seen == [("processing", 1), ("retrying", 1), ("processing", 2), ("retrying", 2), ("processing", 3)]


def test_unreadable_payload_goes_to_dlq(factory):
    worker, _ = processor(factory)
    for bad in (b"nope", b"{}", b'{"id": "x"}', b'{"id": true}', b"[1]"):
        assert asyncio.run(worker.handle(bad)) == "dead"


def test_missing_row_is_dropped(factory):
    worker, _ = processor(factory)
    assert asyncio.run(worker.handle(body(999))) == "dropped"


def test_row_cleared_mid_processing_is_dropped(factory):
    event_id = repo.create_notification(factory, 1, "x", "b")

    async def sleep(seconds):
        repo.remove_event(factory, event_id)

    worker = NotificationProcessor(factory, sleep=sleep, work_time=lambda: 0)
    # first status update succeeds, the row vanishes during the work, the DONE update finds nothing
    assert asyncio.run(worker.handle(body(event_id))) == "done"
    assert status_of_missing(factory, event_id)


def status_of_missing(factory, event_id):
    with factory() as db:
        return db.get(LabEvent, event_id) is None


def test_row_removed_before_first_update_is_dropped(factory, monkeypatch):
    event_id = repo.create_notification(factory, 1, "x", "b")
    monkeypatch.setattr(repo, "set_notification_status", lambda *a: False)
    worker, _ = processor(factory)
    assert asyncio.run(worker.handle(body(event_id))) == "dropped"


def test_default_work_time_is_within_range():
    from app.processing import WORK_SECONDS, _work_time

    assert all(WORK_SECONDS[0] <= _work_time() <= WORK_SECONDS[1] for _ in range(20))


# --- log writer -----------------------------------------------------------------------------------------------


def log_value(**over):
    data = {"userId": 7, "level": "warn", "message": "disk"} | over
    return json.dumps(data).encode()


def test_log_writer_stores_with_partition_offset_and_timestamp(factory):
    writer = LogWriter(factory)
    assert asyncio.run(writer.handle(0, 41, log_value(), 1_700_000_000_000)) is True
    [row] = repo.list_logs(factory, 7, 10)
    assert (row["level"], row["message"], row["partition"], row["offset"]) == ("warn", "disk", 0, 41)
    assert row["createdAt"].startswith("2023-11-14")


def test_log_writer_is_idempotent_for_redelivery(factory):
    writer = LogWriter(factory)
    assert asyncio.run(writer.handle(0, 1, log_value())) is True
    assert asyncio.run(writer.handle(0, 1, log_value())) is False
    assert len(repo.list_logs(factory, 7, 10)) == 1


@pytest.mark.parametrize(
    "value",
    [
        b"nope",
        b"{}",
        log_value(userId=0),
        log_value(userId="7"),
        log_value(userId=True),
        log_value(level="debug"),
        log_value(message=5),
        log_value(message="x" * 201),
    ],
)
def test_log_writer_skips_bad_messages(factory, value):
    assert asyncio.run(LogWriter(factory).handle(0, 1, value)) is False
    assert repo.list_logs(factory, 7, 10) == []
    assert parse_log_value(value) is None


def test_replay_message_formats_and_rejects():
    ok = replay_message(LogRecord("7", 0, 3, log_value(), 1_700_000_000_000))
    assert ok["offset"] == 3 and ok["level"] == "warn" and ok["timestamp"].startswith("2023-11-14")
    assert replay_message(LogRecord("7", 0, 3, b"x", 0)) is None
