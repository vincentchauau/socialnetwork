import asyncio
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import make_engine
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
    assert main._start_account_consumer("f") == ("face", "f")


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


def test_lifespan_stops_consumer(monkeypatch):
    stopped = []

    class Handle:
        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(main, "_start_account_consumer", lambda factory: Handle())
    with TestClient(main.create_app("sqlite://")):
        pass
    assert stopped == [True]


def test_make_engine_variants(tmp_path):
    assert make_engine("sqlite://").dialect.name == "sqlite"
    assert make_engine(f"sqlite:///{tmp_path / 'f.db'}").dialect.name == "sqlite"
    assert make_engine("postgresql+psycopg://u:p@h/db").dialect.name == "postgresql"


def test_check_origin_ignores_safe_methods():
    request = types.SimpleNamespace(method="GET", headers={"origin": "https://evil"})
    assert check_origin(request) is None
