import asyncio
import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import main, repo, worker
from app.account_events import on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.limits import UserRateLimiter
from app.security import check_origin


def test_consumer_not_started_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert main._start_account_consumer(object()) is None
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("TESTING", "1")
    assert main._start_account_consumer(object()) is None


def test_consumer_started_with_redis(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://x")
    fake = types.ModuleType("sn_shared.events")
    fake.start_account_consumer = lambda name, factory: (name, factory)
    monkeypatch.setitem(sys.modules, "sn_shared.events", fake)
    assert main._start_account_consumer("f") == ("lab", "f")


def test_consumer_import_error(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setitem(sys.modules, "sn_shared.events", None)
    assert main._start_account_consumer(object()) is None


def test_stop_consumer_variants():
    calls = []

    class Sync:
        def stop(self):
            calls.append("sync")

    class Async:
        async def close(self):
            calls.append("async")

    asyncio.run(main._stop_account_consumer(Sync()))
    asyncio.run(main._stop_account_consumer(Async()))
    asyncio.run(main._stop_account_consumer(object()))
    assert calls == ["sync", "async"]


def test_lifespan_stops_consumer(monkeypatch, fakes):
    stopped = []

    class Handle:
        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(main, "_start_account_consumer", lambda factory: Handle())
    with TestClient(main.create_app("sqlite://", fakes)):
        pass
    assert stopped == [True]


def test_app_starts_with_real_clients_and_no_brokers(monkeypatch, alice):
    """The default clients connect lazily: no Redis/RabbitMQ/Kafka/gRPC at all -> still starts, status all false."""
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("GRPC_USER_TARGET", "127.0.0.1:1")
    monkeypatch.setenv("RABBITMQ_HOST", "127.0.0.1")
    monkeypatch.setenv("RABBITMQ_PORT", "1")
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "127.0.0.1:1")
    with TestClient(main.create_app("sqlite://")) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/status", headers=alice).json() == {
            "redis": False, "grpc": False, "rabbitmq": False, "kafka": False, "messaging": False,
        }
        assert client.get("/users/1", headers=alice).status_code == 503
        assert client.post("/notifications", json={"title": "t", "body": "b"}, headers=alice).status_code == 503
        assert client.post("/logs", json={"level": "info", "message": "m"}, headers=alice).status_code == 503
        assert client.get("/logs/replay", headers=alice).status_code == 503


def test_make_engine_variants(tmp_path):
    assert make_engine("sqlite://").dialect.name == "sqlite"
    assert make_engine(f"sqlite:///{tmp_path / 'f.db'}").dialect.name == "sqlite"
    assert make_engine("postgresql+psycopg://u:p@h/db").dialect.name == "postgresql"


def test_check_origin_ignores_safe_methods():
    request = types.SimpleNamespace(method="GET", headers={"origin": "https://evil"})
    assert check_origin(request) is None


def test_rate_limiter_window_and_prune():
    now = [0.0]
    limiter = UserRateLimiter(max_events=2, window=10, clock=lambda: now[0])
    assert limiter.allow(1) and limiter.allow(1) and not limiter.allow(1)
    now[0] = 11
    assert limiter.allow(1)
    from app import limits

    for user in range(limits.PRUNE_AT + 1):
        limiter.allow(1000 + user)
    now[0] = 100
    limiter.allow(5)
    assert len(limiter._events) < limits.PRUNE_AT


# --- account events -------------------------------------------------------------------------------------------


def test_user_deleted_removes_only_that_users_rows_and_is_idempotent():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repo.create_notification(factory, 1, "a", "b")
    repo.create_notification(factory, 2, "c", "d")
    with factory() as db:
        on_user_deleted(db, 1)
        on_user_deleted(db, 1)
        on_user_deleted(db, 0)
        on_user_renamed(db, 2, "new")
        db.commit()
    assert repo.list_notifications(factory, 1, 10) == []
    assert len(repo.list_notifications(factory, 2, 10)) == 1


# --- worker supervision ---------------------------------------------------------------------------------------


def test_supervise_restarts_after_failure_until_stopped():
    async def go():
        stop = asyncio.Event()
        calls = []

        async def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("broker down")
            stop.set()

        await worker.supervise("test", flaky, stop, retry_delay=0.01)
        return len(calls)

    assert asyncio.run(go()) == 2


def test_heartbeat_touches_file(tmp_path):
    async def go():
        stop = asyncio.Event()
        path = tmp_path / "alive"
        task = asyncio.create_task(worker.heartbeat(path, stop, interval=0.01))
        await asyncio.sleep(0.05)
        stop.set()
        await task
        return path.exists()

    assert asyncio.run(go()) is True


def test_heartbeat_ignores_unwritable_path(tmp_path):
    async def go():
        stop = asyncio.Event()
        task = asyncio.create_task(worker.heartbeat(tmp_path / "missing" / "alive", stop, interval=0.01))
        await asyncio.sleep(0.03)
        stop.set()
        await task

    asyncio.run(go())


def test_run_worker_wires_both_consumers(tmp_path):
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    event_id = repo.create_notification(factory, 1, "hello", "b")

    async def go():
        stop = asyncio.Event()
        seen = {}

        async def notifications(handler, stop_event):
            import json

            seen["outcome"] = await handler(json.dumps({"id": event_id}).encode())

        async def logs(handler, stop_event):
            import json

            seen["stored"] = await handler(0, 5, json.dumps({"userId": 1, "level": "info", "message": "m"}).encode(), 0)
            stop.set()

        await worker.run_worker(factory, stop, notifications, logs, tmp_path / "alive", retry_delay=0.01)
        return seen

    seen = asyncio.run(go())
    assert seen["outcome"] == "done" and seen["stored"] is True


@pytest.mark.parametrize("name", ["interfaces", "models", "schemas"])
def test_modules_import(name):
    __import__(f"app.{name}")
