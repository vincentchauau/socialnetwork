import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import create_app  # noqa: E402
from tests.fakes import FakeBiometrics, fake_google_verifier  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    for name in (
        "APP_ENV", "COOKIE_SECURE", "ACCESS_TOKEN_MINUTES", "REFRESH_DAYS", "ALLOWED_ORIGINS",
        "GOOGLE_CLIENT_ID", "BIOMETRICS_ENABLED", "DATA_KEY",
    ):  # fmt: skip
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def fast_scrypt(request, monkeypatch):
    """Cheap scrypt keeps the suite fast; tests marked real_scrypt use the production cost."""
    if "real_scrypt" not in request.keywords:
        monkeypatch.setattr("app.passwords.SCRYPT_N", 2**10)


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


@pytest.fixture
def google_client(client):
    client.app.state.google_verifier = fake_google_verifier
    return client


@pytest.fixture
def bio_client(monkeypatch):
    monkeypatch.setenv("BIOMETRICS_ENABLED", "1")
    monkeypatch.setenv("DATA_KEY", Fernet.generate_key().decode())
    app = create_app("sqlite://")
    app.state.biometrics = FakeBiometrics()
    with TestClient(app) as test_client:
        yield test_client
