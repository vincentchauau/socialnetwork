import time

import pytest

from sn_shared import (
    COOKIE_NAME,
    AuthError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from sn_shared.security import ISSUER, payload_from_cookies
from sn_shared.testing import install_test_keys, sign_claims


@pytest.fixture(autouse=True)
def jwt_keys(monkeypatch):
    install_test_keys(monkeypatch)


def test_password_round_trip():
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_password_rejects_malformed_hash():
    assert not verify_password("pw", "not-a-bcrypt-hash")


def test_token_round_trip():
    payload = decode_token(create_token(7, "alice"))
    assert (payload.user_id, payload.username) == (7, "alice")


def test_expired_token_is_rejected():
    with pytest.raises(AuthError):
        decode_token(create_token(1, "bob", ttl_seconds=-10))


def test_tampered_token_is_rejected():
    with pytest.raises(AuthError):
        decode_token(create_token(1, "bob") + "x")


def test_missing_cookie_is_rejected():
    with pytest.raises(AuthError):
        payload_from_cookies({})


def test_payload_from_cookies():
    payload = payload_from_cookies({COOKIE_NAME: create_token(3, "carol")})
    assert payload.username == "carol"


def test_token_without_issuer_is_rejected():
    now = int(time.time())
    forged = sign_claims({"sub": "1", "username": "bob", "iat": now, "exp": now + 60})
    with pytest.raises(AuthError):
        decode_token(forged)


def test_payload_exposes_expiry():
    payload = decode_token(create_token(1, "bob", ttl_seconds=100))
    assert time.time() < payload.expires_at <= time.time() + 100


def test_token_carries_role_and_version():
    payload = decode_token(create_token(7, "alice", role="admin", ver=3))
    assert (payload.role, payload.ver) == ("admin", 3)


def test_legacy_token_without_role_defaults_to_user():
    payload = decode_token(create_token(7, "alice"))
    assert payload.role == "user"
    assert payload.ver is None


def test_refresh_mfa_and_fresh_tokens_are_not_access_tokens():
    for typ in ("refresh", "mfa", "fresh"):
        token = sign_claims({"iss": ISSUER, "sub": "1", "username": "a", "typ": typ, "exp": 4102444800})
        with pytest.raises(AuthError):
            decode_token(token)


def test_internal_secret_must_be_long_enough(monkeypatch):
    from sn_shared.security import get_jwt_secret

    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        get_jwt_secret()
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    assert get_jwt_secret() == "x" * 40
