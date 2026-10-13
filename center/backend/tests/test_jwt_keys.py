"""Asymmetric access tokens as seen from center: configuration, issuing, and what apps can (not) accept."""

import re

import jwt
import pytest

from app import cli
from app.config import ConfigError
from app.main import create_app
from app.tokens import create_fresh_token, create_mfa_token, create_refresh_token
from sn_shared import AuthError, decode_token, jwtkeys
from sn_shared.testing import keypair
from tests.helpers import CREDS, forge, register

PROD = {"APP_ENV": "production", "COOKIE_SECURE": "1", "WEBAUTHN_RP_ID": "example.com"}


@pytest.fixture(autouse=True)
def fresh_keys():
    jwtkeys.reset()
    yield
    jwtkeys.reset()


def build(monkeypatch, **env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return create_app("sqlite://")


def test_production_without_a_private_key_refuses_to_start(monkeypatch):
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    monkeypatch.delenv("JWT_PUBLIC_KEYS")
    with pytest.raises(ConfigError, match="JWT_PRIVATE_KEY"):
        build(monkeypatch, **PROD)


def test_production_starts_with_a_private_key(monkeypatch):
    assert build(monkeypatch, **PROD) is not None


def test_an_invalid_private_key_refuses_to_start(monkeypatch):
    monkeypatch.setenv("JWT_PRIVATE_KEY", "nonsense")
    with pytest.raises(ConfigError, match="JWT_PRIVATE_KEY"):
        build(monkeypatch)


def test_an_invalid_public_key_list_refuses_to_start(monkeypatch):
    monkeypatch.setenv("JWT_PUBLIC_KEYS", "nonsense")
    with pytest.raises(ConfigError, match="JWT_PUBLIC_KEYS"):
        build(monkeypatch)


def test_development_without_a_key_uses_an_ephemeral_one(monkeypatch, caplog):
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    monkeypatch.delenv("JWT_PUBLIC_KEYS")
    from fastapi.testclient import TestClient

    with caplog.at_level("WARNING", logger="sn.jwtkeys"):
        with TestClient(create_app("sqlite://")) as client:
            register(client)
            assert client.get("/auth/me").status_code == 200
    assert "EPHEMERAL" in caplog.text


def test_the_access_cookie_is_eddsa_and_verifiable_with_the_public_key_alone(client, monkeypatch):
    register(client)
    token = client.cookies.get("sn_token")
    header = jwt.get_unverified_header(token)
    assert header == {"alg": "EdDSA", "typ": "JWT", "kid": keypair()[2]}
    monkeypatch.delenv("JWT_PRIVATE_KEY")  # an app has no private key
    monkeypatch.setenv("JWT_PUBLIC_KEYS", keypair()[1])
    jwtkeys.reset()
    assert decode_token(token).username == CREDS["username"]


def test_internal_center_tokens_stay_hs256_and_apps_refuse_them_as_access_tokens():
    for token in (
        create_refresh_token(1, 0, 600, sid="s" * 32),
        create_mfa_token(1, 0),
        create_fresh_token(1, 0, 600, "s" * 32),
    ):
        assert jwt.get_unverified_header(token)["alg"] == "HS256"
        with pytest.raises(AuthError):
            decode_token(token)


def test_a_legacy_hs256_access_token_is_refused_everywhere(client):
    register(client)
    legacy = forge({"sub": "1", "username": "alice", "role": "user", "ver": 0})
    with pytest.raises(AuthError):
        decode_token(legacy)
    client.cookies.clear()
    client.cookies.set("sn_token", legacy, path="/")
    assert client.get("/auth/me").status_code == 401


def test_gen_jwt_key_output_works_with_the_verifier(monkeypatch, capsys):
    assert cli.main(["gen-jwt-key"]) == 0
    out = capsys.readouterr().out
    private = re.search(r"-----BEGIN PRIVATE KEY-----.+?-----END PRIVATE KEY-----", out, re.S).group(0)
    public = re.search(r"-----BEGIN PUBLIC KEY-----.+?-----END PUBLIC KEY-----", out, re.S).group(0)
    kid = re.search(r"kid[^:]*: (\S+)", out).group(1)
    monkeypatch.setenv("JWT_PRIVATE_KEY", private)
    monkeypatch.setenv("JWT_PUBLIC_KEYS", public)
    jwtkeys.reset()
    from sn_shared import create_token

    token = create_token(9, "zed")
    assert jwt.get_unverified_header(token)["kid"] == kid
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    jwtkeys.reset()
    assert decode_token(token).user_id == 9


def test_gen_jwt_key_makes_a_new_pair_each_time(capsys):
    cli.main(["gen-jwt-key"])
    first = capsys.readouterr().out
    cli.main(["gen-jwt-key"])
    assert capsys.readouterr().out != first


def test_redis_without_app_env_and_without_a_private_key_refuses_to_start(monkeypatch):
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("JWT_PRIVATE_KEY_FILE", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    with pytest.raises(ConfigError, match="APP_ENV"):
        create_app("sqlite://")
    monkeypatch.setenv("APP_ENV", "development")  # explicit development stays possible (compose does this)
    create_app("sqlite://")
