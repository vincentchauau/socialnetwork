"""Test helper: one Ed25519 keypair per process, wired into the environment the way a deployment would.

    from sn_shared.testing import install_test_keys
    install_test_keys()                    # at conftest import time (before create_app())
    install_test_keys(monkeypatch)         # in an autouse fixture, restored after each test
"""

import os

from sn_shared import jwtkeys

import logging
logger = logging.getLogger(__name__)

_pair: tuple[str, str, str] | None = None


def keypair() -> tuple[str, str, str]:
    """(private PEM, public PEM, kid), generated once per process."""
    try:
        global _pair
        if _pair is None:
            _pair = jwtkeys.generate_keypair()
        return _pair
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("keypair failed")
        raise


def install_test_keys(monkeypatch=None) -> None:
    try:
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
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("install_test_keys failed")
        raise


def sign_claims(claims: dict) -> str:
    """An EdDSA token over arbitrary claims, signed like center would (for forging odd tokens in tests)."""
    try:
        import jwt

        signer = jwtkeys.get_signer()
        return jwt.encode(claims, signer.private_key, algorithm=jwtkeys.ACCESS_ALGORITHM, headers={"kid": signer.kid})
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("sign_claims failed")
        raise


def add_person(session_factory, user_id: int, username: str, **fields) -> None:
    """A row of `users` in the database of a test (the table is made by `directory.ensure_table_for_sqlite`): who an app reads
    as a person. `fields` are columns of the profile (`name`, `headline`, `visibility`, `kind`...). Existing rows are changed."""
    try:
        from sn_shared.directory import Person

        with session_factory() as db:
            person = db.get(Person, user_id)
            if person is None:
                person = Person(user_id=user_id, username=username)
                db.add(person)
            person.username = username
            for key, value in fields.items():
                setattr(person, key, value)
            db.commit()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_person failed")
        raise
