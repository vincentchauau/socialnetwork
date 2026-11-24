import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("TESTING", "1")

from sn_shared import directory  # noqa: E402
from sn_shared.db import make_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


@pytest.fixture(autouse=True)
def provider_dummy(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "dummy")


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    """Every test starts with its own hour of replies (the limiter is shared by the process)."""
    from api.chat.agent import service

    monkeypatch.setattr(service, "_limiter", service.Limiter(10_000))


@pytest.fixture
def factory(tmp_path):
    """The sessions of the chat: the people of `users` are read from them, as the chat does."""
    engine = make_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    directory.ensure_table_for_sqlite(engine)
    return sessionmaker(engine, expire_on_commit=False)


SECRET = "s" * 32


class _Response:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code, self._body = status_code, body

    def json(self) -> dict:
        return self._body


class _Client:
    """The tools called as the chat calls them, in process: `client.app.state.http` is the service the tools reach."""

    def __init__(self) -> None:
        from types import SimpleNamespace

        from api.chat.agent import tools

        self.app = SimpleNamespace(state=SimpleNamespace(http=tools._call))

    def post(self, path: str, content: bytes = b"", headers: dict | None = None) -> _Response:
        import json

        from api.chat.agent import service

        body = json.loads(content or b"{}")
        if path != "/tools":
            return _Response(404, {})
        card = service.run_tool(body.get("tool", ""), body.get("args", {}), body.get("caller_id", 1), body.get("token", ""), body.get("confirmed", False), self.app.state.http)
        if card is None:
            return _Response(422, {"detail": "Invalid request"})
        return _Response(200, {"card": card})


@pytest.fixture
def client():
    return _Client()
