import pytest

from sn_shared import (
    COOKIE_NAME,
    AuthError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from sn_shared.security import payload_from_cookies


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 40)


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


def test_token_signed_with_other_secret_is_rejected(monkeypatch):
    token = create_token(1, "bob")
    monkeypatch.setenv("JWT_SECRET", "y" * 40)
    with pytest.raises(AuthError):
        decode_token(token)


def test_short_secret_fails_fast(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        create_token(1, "bob")


def test_missing_cookie_is_rejected():
    with pytest.raises(AuthError):
        payload_from_cookies({})


def test_payload_from_cookies():
    payload = payload_from_cookies({COOKIE_NAME: create_token(3, "carol")})
    assert payload.username == "carol"


def test_token_without_issuer_is_rejected():
    import time

    import jwt

    now = int(time.time())
    forged = jwt.encode(
        {"sub": "1", "username": "bob", "iat": now, "exp": now + 60},
        "x" * 40,
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_token(forged)


def test_payload_exposes_expiry():
    import time

    payload = decode_token(create_token(1, "bob", ttl_seconds=100))
    assert time.time() < payload.expires_at <= time.time() + 100
