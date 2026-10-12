import fakeredis
import pytest
from fastapi import HTTPException

from sn_shared import COOKIE_NAME, AuthError, create_token, decode_token, revocation
from sn_shared.deps import get_current_user
from sn_shared.security import payload_from_cookies


class FakeRequest:
    def __init__(self, token: str) -> None:
        self.cookies = {COOKIE_NAME: token}


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.delenv("REDIS_URL", raising=False)
    yield
    revocation.reset()


@pytest.fixture
def store():
    client = fakeredis.FakeRedis(decode_responses=True)
    revocation.use_client(client)
    return client


class BrokenClient:
    def mget(self, keys):
        raise ConnectionError("down")

    def get(self, key):
        raise ConnectionError("down")

    def set(self, *args, **kwargs):
        raise ConnectionError("down")


def test_token_carries_the_sid():
    assert decode_token(create_token(1, "a", ver=2, sid="ab" * 16)).sid == "ab" * 16
    assert decode_token(create_token(1, "a")).sid is None


def test_a_non_string_sid_is_rejected():
    import jwt

    from sn_shared.security import ALGORITHM, ISSUER

    bad = jwt.encode({"iss": ISSUER, "sub": "1", "username": "a", "exp": 4102444800, "sid": 5}, "x" * 40, algorithm=ALGORITHM)
    with pytest.raises(AuthError):
        decode_token(bad)


def test_without_redis_nothing_is_checked_or_published():
    assert revocation.is_revoked(1, "s" * 32, 0) is False
    assert revocation.publish_session_revoked("s" * 32, 60) is False
    assert revocation.publish_min_version(1, 3, 60) is False
    assert get_current_user(FakeRequest(create_token(1, "a", ver=0, sid="s" * 32))).user_id == 1


def test_a_revoked_sid_is_rejected_by_get_current_user(store):
    token = create_token(1, "a", ver=0, sid="s" * 32)
    assert get_current_user(FakeRequest(token)).user_id == 1
    assert revocation.publish_session_revoked("s" * 32, 3660) is True
    with pytest.raises(HTTPException) as exc:
        get_current_user(FakeRequest(token))
    assert exc.value.status_code == 401
    assert 0 < store.ttl(f"{revocation.SID_PREFIX}{'s' * 32}") <= 3660


def test_other_sessions_stay_valid(store):
    revocation.publish_session_revoked("a" * 32, 60)
    assert payload_from_cookies({COOKIE_NAME: create_token(1, "a", ver=0, sid="b" * 32)}).sid == "b" * 32


def test_min_version_rejects_older_tokens_only(store):
    revocation.publish_min_version(1, 3, 3660)
    for ver in (0, 2):
        with pytest.raises(AuthError):
            payload_from_cookies({COOKIE_NAME: create_token(1, "a", ver=ver)})
    assert payload_from_cookies({COOKIE_NAME: create_token(1, "a", ver=3)}).ver == 3
    assert payload_from_cookies({COOKIE_NAME: create_token(2, "b", ver=0)}).user_id == 2  # another user
    assert payload_from_cookies({COOKIE_NAME: create_token(1, "a")}).ver is None  # legacy token without ver


def test_min_version_never_goes_down(store):
    revocation.publish_min_version(1, 5, 60)
    revocation.publish_min_version(1, 4, 60)
    assert store.get(f"{revocation.MINVER_PREFIX}1") == "5"


def test_a_broken_store_fails_open_and_logs_once(caplog):
    revocation.use_client(BrokenClient())
    token = create_token(1, "a", ver=0, sid="s" * 32)
    with caplog.at_level("ERROR", logger="sn.revocation"):
        assert get_current_user(FakeRequest(token)).user_id == 1
        assert get_current_user(FakeRequest(token)).user_id == 1
        assert revocation.publish_session_revoked("s" * 32, 60) is False
        assert revocation.publish_min_version(1, 1, 60) is False
    assert len([r for r in caplog.records if "failing open" in r.message]) == 1


def test_a_corrupt_minimum_is_treated_as_revoked_and_repaired_by_the_next_publish(store):
    store.set(f"{revocation.MINVER_PREFIX}1", "oops")
    with pytest.raises(AuthError):
        payload_from_cookies({COOKIE_NAME: create_token(1, "a", ver=0)})
    assert revocation.publish_min_version(1, 2, 60) is True
    assert store.get(f"{revocation.MINVER_PREFIX}1") == "2"


def test_a_fresh_token_is_never_an_access_token():
    import jwt

    from sn_shared.security import ALGORITHM, ISSUER

    fresh = jwt.encode(
        {"iss": ISSUER, "sub": "1", "username": "a", "typ": "fresh", "exp": 4102444800}, "x" * 40, algorithm=ALGORITHM
    )
    with pytest.raises(AuthError):
        decode_token(fresh)


def test_publishing_gives_up_when_the_value_keeps_changing_underneath(store):
    from redis.exceptions import WatchError

    class Racing:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def watch(self, key):
            raise WatchError

    class Client:
        def pipeline(self):
            return Racing()

    revocation.use_client(Client())
    assert revocation.publish_min_version(1, 1, 60) is False
    assert revocation.configured() is True


def test_redis_url_builds_a_client_with_a_short_timeout(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    revocation.reset()
    client = revocation._client()
    assert client.connection_pool.connection_kwargs["socket_timeout"] == revocation.SOCKET_TIMEOUT_SECONDS
    assert revocation._client() is client  # cached per URL
    assert revocation.is_revoked(1, "s" * 32, 0) is False  # unreachable: fails open


def test_a_missing_redis_package_is_a_no_op(monkeypatch):
    import builtins

    real = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "redis":
            raise ImportError("no redis")
        return real(name, *args, **kwargs)

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(builtins, "__import__", fake)
    revocation.reset()
    assert revocation.is_revoked(1, "s" * 32, 0) is False
