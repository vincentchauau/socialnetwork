import pytest

from app import passwords
from app.passwords import (
    NO_PASSWORD,
    hash_password,
    has_password,
    needs_rehash,
    password_problem,
    verify_password,
)
from sn_shared import hash_password as bcrypt_hash


@pytest.mark.real_scrypt
def test_hash_format_and_size_fit_the_column():
    stored = hash_password("correct horse")
    scheme, n, r, p, salt, digest = stored.split("$")
    assert (scheme, int(n), int(r), int(p)) == ("scrypt", 2**15, 8, 1)
    assert len(stored) == 86 <= 100  # users.password_hash is String(100)
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert not needs_rehash(stored)


def test_unicode_normalisation_matches_equivalent_forms():
    stored = hash_password("café-pass-1")
    assert verify_password("café-pass-1", stored)


def test_no_password_sentinel_never_verifies():
    assert NO_PASSWORD == "!"
    assert not has_password(NO_PASSWORD)
    assert has_password(hash_password("whatever-1"))
    assert not verify_password("!", NO_PASSWORD)
    assert not verify_password("", NO_PASSWORD)
    assert not needs_rehash(NO_PASSWORD)


@pytest.mark.parametrize("stored", [None, "", "garbage", "scrypt$1$2", "md5$1$1$1$AA==$AA==", "scrypt$x$8$1$AA==$AA=="])
def test_malformed_hashes_are_rejected(stored):
    assert not verify_password("pw", stored)


def test_legacy_bcrypt_hash_verifies_and_wants_rehash():
    legacy = bcrypt_hash("legacy-pass-1")
    assert legacy.startswith("$2")
    assert verify_password("legacy-pass-1", legacy)
    assert not verify_password("other", legacy)
    assert needs_rehash(legacy)


def test_needs_rehash_for_old_scrypt_parameters(monkeypatch):
    stored = hash_password("some-password")
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**11)
    assert needs_rehash(stored)
    assert verify_password("some-password", stored)  # parameters are read from the hash


def test_needs_rehash_on_garbage():
    assert needs_rehash("not-a-hash")


@pytest.mark.parametrize(
    ("password", "username", "fragment"),
    [
        ("short", "", "at least 8"),
        ("x" * 129, "", "at most 128"),
        ("aabbaabb", "", "too simple"),
        ("PASSWORD123", "", "too common"),
        ("Alice-Smith", "alice-smith", "username"),
        ("good-enough-pass", "alice", None),
        ("abcd1234" * 16, "", None),
    ],
)
def test_password_problem(password, username, fragment):
    problem = password_problem(password, username)
    if fragment is None:
        assert problem is None
    else:
        assert fragment in problem
