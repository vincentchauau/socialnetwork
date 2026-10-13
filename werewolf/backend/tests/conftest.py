import os
import random

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:8080")

from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token

ALLOWED_ORIGIN = "http://localhost:8080"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    random.seed(20240607)  # the engine and bots use the global RNG: keep runs reproducible
    install_test_keys(monkeypatch)
    monkeypatch.setenv("ALLOWED_ORIGINS", ALLOWED_ORIGIN)


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


def ws_headers(user_id: int = 1, username: str = "alice", origin: str = ALLOWED_ORIGIN):
    return {**auth_cookie(user_id, username), "Origin": origin}
