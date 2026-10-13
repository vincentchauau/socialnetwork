import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.interfaces import LogRecord, Services, Unavailable  # noqa: E402
from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token  # noqa: E402


class FakeCache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.up = True

    def _check(self) -> None:
        if not self.up:
            raise Unavailable("redis")

    async def get(self, key):
        self._check()
        return self.data.get(key)

    async def set(self, key, value, ttl_seconds):
        self._check()
        self.data[key] = value
        self.ttls[key] = ttl_seconds

    async def delete(self, key):
        self._check()
        self.data.pop(key, None)

    async def ping(self):
        return self.up

    async def close(self):
        pass


class FakeUsers:
    NAMES = {"1": "Alice", "2": "Bob", "3": "Charlie"}

    def __init__(self) -> None:
        self.up = True
        self.calls: list[str] = []

    async def get_user(self, user_id):
        if not self.up:
            raise Unavailable("grpc")
        self.calls.append(user_id)
        return self.NAMES.get(user_id, "Unknown")

    async def ping(self):
        return self.up

    async def close(self):
        pass


class FakeQueue:
    def __init__(self) -> None:
        self.up = True
        self.published: list[bytes] = []

    async def publish(self, payload):
        if not self.up:
            raise Unavailable("rabbitmq")
        self.published.append(payload)

    async def ping(self):
        return self.up

    async def close(self):
        pass


class FakeLogs:
    def __init__(self) -> None:
        self.up = True
        self.messages: list[tuple[str, bytes]] = []

    async def publish(self, key, value):
        if not self.up:
            raise Unavailable("kafka")
        self.messages.append((key, value))
        return 0, len(self.messages) - 1

    async def replay(self, key, limit):
        if not self.up:
            raise Unavailable("kafka")
        records = [LogRecord(k, 0, i, v, 1_700_000_000_000 + i) for i, (k, v) in enumerate(self.messages)]
        return records[: limit + 5]  # deliberately returns other users' records too: the route must filter

    async def ping(self):
        return self.up

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    install_test_keys(monkeypatch)


@pytest.fixture
def fakes() -> Services:
    return Services(cache=FakeCache(), users=FakeUsers(), queue=FakeQueue(), logs=FakeLogs())


@pytest.fixture
def client(fakes: Services) -> Iterator[TestClient]:
    with TestClient(create_app("sqlite://", fakes)) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


@pytest.fixture
def alice() -> dict[str, str]:
    return auth_cookie(1, "alice")


@pytest.fixture
def bob() -> dict[str, str]:
    return auth_cookie(2, "bob")
