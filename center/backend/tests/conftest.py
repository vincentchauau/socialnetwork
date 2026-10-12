import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import create_app  # noqa: E402
from sn_shared import revocation  # noqa: E402
from tests.fakes import FakeBiometrics, FakeMailer, fake_google_verifier  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    install_test_keys(monkeypatch)
    for name in (
        "APP_ENV", "COOKIE_SECURE", "ACCESS_TOKEN_MINUTES", "REFRESH_DAYS", "ALLOWED_ORIGINS",
        "GOOGLE_CLIENT_ID", "BIOMETRICS_ENABLED", "DATA_KEY", "WEBAUTHN_RP_ID", "WEBAUTHN_RP_NAME",
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_STARTTLS", "PUBLIC_URL",
        "SMTP_SSL", "SMTP_ALLOW_PLAINTEXT_AUTH", "REDIS_URL",
    ):  # fmt: skip
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_revocation_store():
    """No cross-app revocation store unless a test installs one (tests that do get a clean slate afterwards)."""
    revocation.reset()
    revocation.use_client(None)
    yield
    revocation.reset()


@pytest.fixture
def revocations():
    """An in-memory Redis standing in for the revocation store shared with the other apps."""
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    revocation.use_client(client)
    return client


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


PUBLIC_URL = "https://app.example"


def _mail_app(monkeypatch, database_url="sqlite://"):
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("PUBLIC_URL", PUBLIC_URL)
    app = create_app(database_url)
    app.state.mailer = FakeMailer()
    app.state.google_verifier = fake_google_verifier
    return app


@pytest.fixture
def mail_client(monkeypatch):
    """Email enabled (fake mailer in app.state.mailer, PUBLIC_URL fixed, fake Google verifier)."""
    with TestClient(_mail_app(monkeypatch)) as test_client:
        yield test_client


@pytest.fixture
def mail_bio_client(monkeypatch):
    monkeypatch.setenv("BIOMETRICS_ENABLED", "1")
    monkeypatch.setenv("DATA_KEY", Fernet.generate_key().decode())
    app = _mail_app(monkeypatch)
    app.state.biometrics = FakeBiometrics()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mail_file_client(monkeypatch, tmp_path):
    """Like mail_client on a file database (real connections per thread, for concurrency tests)."""
    with TestClient(_mail_app(monkeypatch, f"sqlite:///{tmp_path / 'mail.db'}")) as test_client:
        yield test_client
