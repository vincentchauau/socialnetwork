import os

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client
