import asyncio

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import create_app


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_startup_requires_verification_keys(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_PUBLIC_KEYS", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("JWT_PUBLIC_KEYS_FILE", raising=False)
    from sn_shared import jwtkeys

    jwtkeys.reset()
    with pytest.raises(Exception):
        create_app("sqlite://")


def test_consumer_is_skipped_in_tests_and_without_redis(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    assert main._start_account_consumer(None) is None
    monkeypatch.delenv("TESTING")
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert main._start_account_consumer(None) is None


def test_consumer_is_started_with_redis_and_stopped_on_shutdown(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6379/0")
    events = []

    class Handle:
        def stop(self):
            events.append("stopped")

    import sn_shared.events as shared_events

    monkeypatch.setattr(shared_events, "start_account_consumer", lambda name, factory: events.append(name) or Handle())
    with TestClient(create_app("sqlite://")):
        assert events == ["work"]
    assert events == ["work", "stopped"]


def test_stop_helper_handles_async_and_missing_stop():
    calls = []

    class AsyncHandle:
        async def close(self):
            calls.append("closed")

    asyncio.run(main._stop_account_consumer(AsyncHandle()))
    asyncio.run(main._stop_account_consumer(object()))
    assert calls == ["closed"]


def test_unexpected_exceptions_do_not_leak_details(client, alice, monkeypatch):
    from app import paths

    def boom(*args, **kwargs):
        raise paths.PathError("Đường dẫn không hợp lệ")

    monkeypatch.setattr("app.files.resolve", boom)
    assert client.get("/files", headers=alice).json() == {"detail": "Đường dẫn không hợp lệ"}
