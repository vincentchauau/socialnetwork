import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sn_shared import AuthError, create_token, decode_token, jwtkeys
from sn_shared.security import INTERNAL_ALGORITHM, ISSUER
from sn_shared.testing import install_test_keys, keypair, sign_claims


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)
    monkeypatch.delenv("APP_ENV", raising=False)
    yield
    jwtkeys.reset()


def _as_signer(monkeypatch, private, kid=None):
    monkeypatch.setenv("JWT_PRIVATE_KEY", private)
    monkeypatch.delenv("JWT_KEY_ID", raising=False)
    if kid:
        monkeypatch.setenv("JWT_KEY_ID", kid)
    jwtkeys.reset()


def _verify_only(monkeypatch, *publics):
    """Behave like an app: public keys only, no private key."""
    monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("JWT_PUBLIC_KEYS", "\n".join(publics))
    jwtkeys.reset()


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _hs256(claims: dict, secret: str, header_extra: dict | None = None) -> str:
    header = {"alg": "HS256", "typ": "JWT", **(header_extra or {})}
    body = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(claims).encode())}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{b64(sig)}"


def _claims(**extra):
    return {"iss": ISSUER, "sub": "1", "username": "bob", "exp": int(time.time()) + 60, **extra}


def _pem_private(key) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def test_token_header_carries_alg_and_kid():
    header = jwt.get_unverified_header(create_token(1, "bob"))
    assert header["alg"] == "EdDSA" and header["kid"] == keypair()[2]


def test_an_app_verifies_with_only_the_public_key_and_cannot_sign(monkeypatch):
    token = create_token(1, "bob")
    _verify_only(monkeypatch, keypair()[1])
    monkeypatch.setenv("APP_ENV", "production")
    assert decode_token(token).username == "bob"
    with pytest.raises(RuntimeError):
        create_token(1, "bob")


def test_rotation_accepts_both_keys_then_rejects_the_removed_one(monkeypatch):
    old_pub = keypair()[1]
    new_priv, new_pub, _ = jwtkeys.generate_keypair()
    old_token = create_token(1, "bob")
    _as_signer(monkeypatch, new_priv)
    new_token = create_token(2, "amy")
    _verify_only(monkeypatch, old_pub, new_pub)  # step 1: apps know both keys
    assert decode_token(old_token).user_id == 1 and decode_token(new_token).user_id == 2
    _verify_only(monkeypatch, new_pub)  # step 3: the old key is retired
    assert decode_token(new_token).user_id == 2
    with pytest.raises(AuthError):
        decode_token(old_token)


def test_unknown_kid_is_rejected(monkeypatch):
    other_priv, _, _ = jwtkeys.generate_keypair()
    _as_signer(monkeypatch, other_priv)
    token = create_token(1, "bob")
    _verify_only(monkeypatch, keypair()[1])
    with pytest.raises(AuthError):
        decode_token(token)


def test_token_signed_by_a_different_private_key_under_a_known_kid_is_rejected(monkeypatch):
    other = serialization.load_pem_private_key(jwtkeys.generate_keypair()[0].encode(), None)
    forged = jwt.encode(_claims(), other, algorithm="EdDSA", headers={"kid": keypair()[2]})
    _verify_only(monkeypatch, keypair()[1])
    with pytest.raises(AuthError):
        decode_token(forged)


def test_token_without_kid_is_rejected():
    key = serialization.load_pem_private_key(keypair()[0].encode(), None)
    with pytest.raises(AuthError):
        decode_token(jwt.encode(_claims(), key, algorithm="EdDSA"))


def test_hs256_signed_with_the_public_key_text_is_refused(monkeypatch):
    public = keypair()[1]
    _verify_only(monkeypatch, public)
    for secret in (public, public.strip(), "x" * 40):
        with pytest.raises(AuthError):
            decode_token(_hs256(_claims(), secret, {"kid": keypair()[2]}))


def test_center_internal_hs256_tokens_are_not_access_tokens():
    token = jwt.encode(_claims(typ="refresh", ver=0), "s" * 40, algorithm=INTERNAL_ALGORITHM)
    with pytest.raises(AuthError):
        decode_token(token)


def test_alg_none_is_refused():
    header = b64(json.dumps({"alg": "none", "typ": "JWT", "kid": keypair()[2]}).encode())
    body = b64(json.dumps(_claims()).encode())
    for token in (f"{header}.{body}.", f"{header}.{body}"):
        with pytest.raises(AuthError):
            decode_token(token)


def test_tampered_payload_is_rejected():
    head, _, sig = create_token(1, "bob").split(".")
    evil = b64(json.dumps(_claims(sub="99", group="admin")).encode())
    with pytest.raises(AuthError):
        decode_token(f"{head}.{evil}.{sig}")


def test_wrong_issuer_and_expired_are_rejected():
    with pytest.raises(AuthError):
        decode_token(sign_claims(_claims(iss="someone-else")))
    with pytest.raises(AuthError):
        decode_token(sign_claims(_claims(exp=int(time.time()) - 5)))


def test_custom_kid_is_matched_through_a_kid_label(monkeypatch):
    private, public, _ = keypair()
    _as_signer(monkeypatch, private, kid="2026-01")
    token = create_token(1, "bob")
    assert jwt.get_unverified_header(token)["kid"] == "2026-01"
    _verify_only(monkeypatch, f"kid: 2026-01\n{public}")
    assert decode_token(token).user_id == 1
    _verify_only(monkeypatch, public)  # no label: the key is known only by its thumbprint
    with pytest.raises(AuthError):
        decode_token(token)


def test_bad_custom_kid_is_a_config_error(monkeypatch):
    monkeypatch.setenv("JWT_KEY_ID", "bad kid!")
    with pytest.raises(RuntimeError):
        jwtkeys.get_signer()


def test_keys_from_files_and_escaped_newlines(monkeypatch, tmp_path):
    private, public, _ = keypair()
    (tmp_path / "priv.pem").write_text(private)
    (tmp_path / "pub.pem").write_text(public)
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    monkeypatch.delenv("JWT_PUBLIC_KEYS")
    monkeypatch.setenv("JWT_PRIVATE_KEY_FILE", str(tmp_path / "priv.pem"))
    monkeypatch.setenv("JWT_PUBLIC_KEYS_FILE", str(tmp_path / "pub.pem"))
    jwtkeys.reset()
    assert decode_token(create_token(4, "dee")).user_id == 4
    monkeypatch.delenv("JWT_PRIVATE_KEY_FILE")
    monkeypatch.delenv("JWT_PUBLIC_KEYS_FILE")
    monkeypatch.setenv("JWT_PRIVATE_KEY", private.strip().replace("\n", "\\n"))
    jwtkeys.reset()
    assert decode_token(create_token(5, "eve")).user_id == 5


def test_unreadable_or_invalid_key_material_is_a_config_error(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_PUBLIC_KEYS_FILE", str(tmp_path / "missing.pem"))
    with pytest.raises(RuntimeError):
        jwtkeys.get_verification_keys()
    monkeypatch.delenv("JWT_PUBLIC_KEYS_FILE")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "not a key")
    with pytest.raises(RuntimeError):
        jwtkeys.get_signer()
    rsa_pub = rsa.generate_private_key(65537, 2048).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    monkeypatch.setenv("JWT_PUBLIC_KEYS", rsa_pub)
    with pytest.raises(RuntimeError):
        jwtkeys.get_verification_keys()
    monkeypatch.setenv("JWT_PUBLIC_KEYS", "garbage")
    with pytest.raises(RuntimeError):
        jwtkeys.get_verification_keys()
    monkeypatch.setenv("JWT_PUBLIC_KEYS", "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----")
    with pytest.raises(RuntimeError):
        jwtkeys.get_verification_keys()


def test_rsa_private_key_is_refused(monkeypatch):
    monkeypatch.setenv("JWT_PRIVATE_KEY", _pem_private(rsa.generate_private_key(65537, 2048)))
    with pytest.raises(RuntimeError):
        jwtkeys.get_signer()


def test_production_requires_keys(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    monkeypatch.delenv("JWT_PUBLIC_KEYS")
    jwtkeys.reset()
    with pytest.raises(RuntimeError, match="JWT_PRIVATE_KEY"):
        jwtkeys.get_signer()
    with pytest.raises(RuntimeError, match="JWT_PUBLIC_KEYS"):
        jwtkeys.require_verification_keys()


def test_development_without_keys_uses_an_ephemeral_signer(monkeypatch, caplog):
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    monkeypatch.delenv("JWT_PUBLIC_KEYS")
    jwtkeys.reset()
    with caplog.at_level("WARNING", logger="sn.jwtkeys"):
        token = create_token(1, "bob")
    assert "EPHEMERAL" in caplog.text
    assert decode_token(token).user_id == 1  # center trusts its own key


def test_app_without_keys_in_development_refuses_every_token(monkeypatch):
    token = create_token(1, "bob")
    monkeypatch.delenv("JWT_PRIVATE_KEY")
    monkeypatch.delenv("JWT_PUBLIC_KEYS")
    jwtkeys.reset()
    jwtkeys.require_verification_keys()  # only warns
    with pytest.raises(AuthError):
        decode_token(token)
