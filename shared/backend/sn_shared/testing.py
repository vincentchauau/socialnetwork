"""Test helper: one Ed25519 keypair per process, wired into the environment the way a deployment would.

    from sn_shared.testing import install_test_keys
    install_test_keys()                    # at conftest import time (before create_app())
    install_test_keys(monkeypatch)         # in an autouse fixture, restored after each test
"""

import os

from sn_shared import jwtkeys

_pair: tuple[str, str, str] | None = None


def keypair() -> tuple[str, str, str]:
    """(private PEM, public PEM, kid), generated once per process."""
    global _pair
    if _pair is None:
        _pair = jwtkeys.generate_keypair()
    return _pair


def install_test_keys(monkeypatch=None) -> None:
    private, public, _ = keypair()
    for name in ("JWT_PRIVATE_KEY_FILE", "JWT_PUBLIC_KEYS_FILE", "JWT_KEY_ID"):
        if monkeypatch is not None:
            monkeypatch.delenv(name, raising=False)
        else:
            os.environ.pop(name, None)
    for name, value in (("JWT_PRIVATE_KEY", private), ("JWT_PUBLIC_KEYS", public)):
        if monkeypatch is not None:
            monkeypatch.setenv(name, value)
        else:
            os.environ.setdefault(name, value)
    jwtkeys.reset()


def sign_claims(claims: dict) -> str:
    """An EdDSA token over arbitrary claims, signed like center would (for forging odd tokens in tests)."""
    import jwt

    signer = jwtkeys.get_signer()
    return jwt.encode(claims, signer.private_key, algorithm=jwtkeys.ACCESS_ALGORITHM, headers={"kid": signer.kid})
