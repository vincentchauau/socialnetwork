import logging

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.center.config import ConfigError, Settings
from api.center.main import create_app
from tests.center.helpers import CREDS, STRONG, csrf, register, grant_fresh

SECRETS = ("S3cret-Pass", "wrong-password", STRONG, "eyJ")  # passwords and the start of any JWT


def build(monkeypatch, **env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return create_app("sqlite://")


# --- production mode ----------------------------------------------------------------------------


def test_development_exposes_docs(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_production_requires_secure_cookies(monkeypatch):
    with pytest.raises(ConfigError, match="COOKIE_SECURE"):
        build(monkeypatch, APP_ENV="production")


def test_production_requires_a_long_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        build(monkeypatch, APP_ENV="production", COOKIE_SECURE="1")


def test_production_disables_docs(monkeypatch):
    client = TestClient(build(monkeypatch, APP_ENV="production", COOKIE_SECURE="1", WEBAUTHN_RP_ID="example.com"))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    ("name", "value"),
    [("APP_ENV", "staging"), ("ACCESS_TOKEN_MINUTES", "soon"), ("REFRESH_DAYS", "0"), ("AUDIO_THRESHOLD", "high")],
)
def test_bad_environment_values_are_rejected(monkeypatch, name, value):
    with pytest.raises(ConfigError, match=name):
        build(monkeypatch, **{name: value})


def test_settings_defaults(monkeypatch):
    settings = Settings.from_env()
    assert (settings.env, settings.cookie_secure, settings.access_minutes, settings.refresh_days) == (
        "development", False, 60, 14,
    )  # fmt: skip
    assert settings.allowed_origins == ("http://localhost:8080",) and not settings.biometrics_enabled


def test_biometric_thresholds_come_from_env(monkeypatch):
    monkeypatch.setenv("FACE_THRESHOLD", "0.5")
    assert Settings.from_env().face_threshold == 0.5


# --- headers, body limit, validation errors -------------------------------------------------------


def test_security_headers_and_no_store_on_auth(client):
    auth = client.get("/auth/config")
    assert auth.headers["x-content-type-options"] == "nosniff"
    assert auth.headers["x-frame-options"] == "DENY"
    assert auth.headers["referrer-policy"] == "no-referrer"
    assert auth.headers["cache-control"] == "no-store"
    health = client.get("/health")
    assert health.headers["x-frame-options"] == "DENY" and "cache-control" not in health.headers


def test_oversized_json_body_is_413(client):
    big = {"username": "alice", "password": "p" * 70_000}
    assert client.post("/auth/login", json=big).status_code == 413


def test_chunked_body_without_content_length_is_413(client):
    def chunks():
        for _ in range(80):
            yield b"x" * 1024

    response = client.post("/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"detail": "Request too large"}


def test_biometric_routes_allow_big_uploads_only_when_enabled(client, bio_client):  # client first: env flag is set later
    payload = {"audio": ("a.webm", b"x" * 100_000)}  # over the 64 KB default
    assert client.post("/auth/me/voice", files=payload).status_code == 413
    session = register(bio_client)
    response = bio_client.post("/auth/me/voice", data={"password": CREDS["password"]}, files=payload, headers=csrf(session))
    assert response.status_code == 200
    huge = {"audio": ("a.webm", b"x" * (16 * 1024 * 1024 + 10))}
    assert bio_client.post("/auth/me/voice", files=huge, headers=csrf(session)).status_code == 413


def test_validation_errors_use_the_detail_envelope(client):
    for body in ({}, {"username": "alice"}, {"username": 5, "password": "x"}):
        response = client.post("/auth/register", json=body)
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
    assert client.post("/auth/login", content=b"{", headers={"Content-Type": "application/json"}).status_code == 422


# --- audit log --------------------------------------------------------------------------------


def test_audit_log_records_events_but_never_secrets(client, caplog):
    caplog.set_level(logging.INFO, logger="auth.audit")
    session = register(client)
    client.post("/auth/login", json={**CREDS, "password": "wrong-password"})
    # Use the CSRF token of the newest login: the cookie was just replaced, and the old token only
    # still matches when both sessions happen to be issued within the same second.
    latest = client.post("/auth/login", json=CREDS).json()
    client.post("/auth/me/password", json={"current_password": CREDS["password"], "new_password": STRONG}, headers=csrf(latest))
    token = client.cookies.get("sn_token")
    client.post("/auth/logout", headers=csrf(client.get("/auth/me").json()))

    text = "\n".join(record.getMessage() for record in caplog.records)
    for event in ("register", "login failed", "login ok", "password changed", "logout"):
        assert event in text, event
    for secret in (*SECRETS, token, session["csrf_token"]):
        assert secret not in text
    assert all(record.name == "auth.audit" for record in caplog.records)


def test_audit_log_covers_lockout_refresh_origin_and_delete(client, caplog):
    from tests.center.helpers import refresh_with, cookie_value

    caplog.set_level(logging.INFO, logger="auth.audit")
    response = client.post("/auth/register", json=CREDS)
    refresh = cookie_value(response, "sn_refresh")
    refresh_with(client, refresh)
    client.post("/auth/login", json=CREDS, headers={"Origin": "https://evil.example"})
    for _ in range(6):
        client.post("/auth/login", json={**CREDS, "password": "wrong-password"})
    me = client.get("/auth/me").json()
    client.request("DELETE", "/auth/me", json={"password": CREDS["password"]}, headers=csrf(me))
    refresh_with(client, "bad")

    text = "\n".join(record.getMessage() for record in caplog.records)
    for event in ("refresh ok", "refresh rejected", "blocked origin", "login locked", "account deleted"):
        assert event in text, event
    for secret in (*SECRETS, refresh):
        assert secret not in text


def test_audit_log_never_contains_google_tokens_or_embeddings(bio_client, caplog):
    from tests.center.fakes import fake_google_verifier

    caplog.set_level(logging.INFO, logger="auth.audit")
    bio_client.app.state.google_verifier = fake_google_verifier
    bio_client.post("/auth/google", json={"id_token": "bad-token-value"})
    session = bio_client.post("/auth/google", json={"id_token": "sub-77|zed@example.com"}).json()
    grant_fresh(bio_client)
    bio_client.post(
        "/auth/me/voice",
        files={"audio": ("a.webm", b"very-secret-audio-bytes")},
        headers=csrf(session),
    )
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "google register" in text and "voice sign-in enabled" in text and "google token rejected" in text
    for secret in ("bad-token-value", "sub-77|zed", "very-secret-audio", "A:very-secret"):
        assert secret not in text


# --- misc ---------------------------------------------------------------------------------------


def test_fernet_key_fixture_is_valid():
    Fernet(Fernet.generate_key())
