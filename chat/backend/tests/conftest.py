import os

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token

ALLOWED_ORIGIN = "http://localhost:8080"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    monkeypatch.setenv("ALLOWED_ORIGINS", ALLOWED_ORIGIN)


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


def ws_headers(user_id: int = 1, username: str = "alice", origin: str = ALLOWED_ORIGIN):
    return {**auth_cookie(user_id, username), "Origin": origin}
