import os

import pytest

from sn_shared import jwtkeys


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in ("JWT_PRIVATE_KEY", "JWT_PRIVATE_KEY_FILE", "JWT_PUBLIC_KEYS", "JWT_PUBLIC_KEYS_FILE", "JWT_KEY_ID"):
        monkeypatch.delenv(n, raising=False)
    jwtkeys.reset()
    yield
    jwtkeys.reset()


def test_duplicate_custom_kid_with_different_keys_is_an_error():
    _, pub1, _ = jwtkeys.generate_keypair()
    _, pub2, _ = jwtkeys.generate_keypair()
    with pytest.raises(RuntimeError, match="more than once"):
        jwtkeys.parse_public_keys(f"kid: a\n{pub1}\nkid: a\n{pub2}")


def test_same_key_listed_twice_is_harmless():
    _, pub, _ = jwtkeys.generate_keypair()
    assert len(jwtkeys.parse_public_keys(f"{pub}\n{pub}")) == 1


def test_jwt_key_id_colliding_with_a_listed_kid_is_an_error(monkeypatch):
    priv, _, _ = jwtkeys.generate_keypair()
    _, other, _ = jwtkeys.generate_keypair()
    monkeypatch.setenv("JWT_PRIVATE_KEY", priv)
    monkeypatch.setenv("JWT_KEY_ID", "k1")
    monkeypatch.setenv("JWT_PUBLIC_KEYS", f"kid: k1\n{other}")
    with pytest.raises(RuntimeError, match="collides"):
        jwtkeys.get_verification_keys()


def test_own_key_listed_under_its_kid_is_fine(monkeypatch):
    priv, pub, kid = jwtkeys.generate_keypair()
    monkeypatch.setenv("JWT_PRIVATE_KEY", priv)
    monkeypatch.setenv("JWT_PUBLIC_KEYS", pub)
    assert kid in jwtkeys.get_verification_keys()


def test_file_cache_notices_same_mtime_replacement(tmp_path, monkeypatch):
    f = tmp_path / "pub.pem"
    _, a, ka = jwtkeys.generate_keypair()
    _, b, kb = jwtkeys.generate_keypair()
    f.write_text(a)
    st = os.stat(f)
    monkeypatch.setenv("JWT_PUBLIC_KEYS_FILE", str(f))
    assert list(jwtkeys.get_verification_keys()) == [ka]
    f.write_text(b + "\n")  # different size
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert list(jwtkeys.get_verification_keys()) == [kb]
