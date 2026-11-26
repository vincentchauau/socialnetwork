import asyncio
import sys
import types

import pytest
from fastapi.testclient import TestClient

from sn_shared.consumer import start_consumer
from api.face import main
from api.face.db import make_engine
from sn_shared.origin import check_origin


def test_consumer_not_started_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert start_consumer("face", object()) is None
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("TESTING", "1")
    assert start_consumer("face", object()) is None


def test_consumer_started_with_redis(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://x")
    fake = types.ModuleType("sn_shared.events")
    fake.start_account_consumer = lambda name, factory, **_: (name, factory)
    monkeypatch.setitem(sys.modules, "sn_shared.events", fake)
    assert start_consumer("face", "f") == ("face", "f")


def test_consumer_import_error(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setitem(sys.modules, "sn_shared.events", None)
    assert start_consumer("face", object()) is None


def test_stop_consumer_variants():
    calls = []

    class Sync:
        def stop(self):
            calls.append("sync")

    class Async:
        async def close(self):
            calls.append("async")

    asyncio.run(main.stop_account_consumer(Sync()))
    asyncio.run(main.stop_account_consumer(Async()))
    asyncio.run(main.stop_account_consumer(object()))
    assert calls == ["sync", "async"]


def test_lifespan_stops_consumer(monkeypatch):
    stopped = []

    class Handle:
        def stop(self):
            stopped.append(True)

    monkeypatch.setattr(main, "start_consumer", lambda name, factory: Handle())
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
