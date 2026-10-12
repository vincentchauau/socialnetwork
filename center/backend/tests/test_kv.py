import logging
import threading

import fakeredis
import pytest
import redis
from fastapi.testclient import TestClient

from app import main as app_main
from app import passkeys as pk
from app.config import ConfigError, Settings
from app.kv import KEY_PREFIX, MemoryKv, RedisKv, ResilientKv, make_kv
from app.throttle import AttemptThrottle
from tests.helpers import CREDS

WINDOW = 60.0


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _redis_client(server: fakeredis.FakeServer | None = None) -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(server=server or fakeredis.FakeServer(), decode_responses=True)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture(params=["memory", "redis"])
def kv(request, clock):
    if request.param == "memory":
        return MemoryKv(now=clock)
    return RedisKv(_redis_client(), now=clock)


# --- behaviour parity: the same matrix runs against both implementations ---


def test_hit_counts_events_inside_the_window(kv, clock):
    assert [kv.hit("a", WINDOW) for _ in range(3)] == [1, 2, 3]
    assert kv.count("a", WINDOW) == 3 and kv.count("b", WINDOW) == 0


def test_events_expire_after_the_window(kv, clock):
    kv.hit("a", WINDOW)
    clock.t += 30
    kv.hit("a", WINDOW)
    clock.t += 31  # the first is now 61 s old, the second 31 s
    assert kv.count("a", WINDOW) == 1
    clock.t += 30
    assert kv.count("a", WINDOW) == 0


def test_clear_forgets_a_key(kv):
    kv.hit("a", WINDOW)
    kv.set_if_absent("a", WINDOW)
    kv.clear("a")
    assert kv.count("a", WINDOW) == 0
    assert kv.set_if_absent("a", WINDOW)


def test_hit_capped_stops_counting_at_the_limit(kv):
    assert [kv.hit_capped("a", WINDOW, 2) for _ in range(4)] == [True, True, False, False]
    assert kv.count("a", WINDOW) == 2


def test_set_if_absent_is_single_use(kv):
    assert kv.set_if_absent("jti", WINDOW)
    assert not kv.set_if_absent("jti", WINDOW)
    assert kv.set_if_absent("other", WINDOW)


def test_tracked_keys_counts_by_prefix(kv):
    kv.hit("x:1", WINDOW)
    kv.hit("x:2", WINDOW)
    kv.hit("y:1", WINDOW)
    assert kv.tracked_keys("x:") == 2 and kv.tracked_keys() == 3


def test_concurrent_hits_never_lose_a_count(kv):
    threads, per_thread = 8, 25
    results: list[int] = []

    def work() -> None:
        results.extend(kv.hit("busy", WINDOW) for _ in range(per_thread))

    workers = [threading.Thread(target=work) for _ in range(threads)]
    [w.start() for w in workers]
    [w.join() for w in workers]

    assert kv.count("busy", WINDOW) == threads * per_thread
    assert sorted(results) == list(range(1, threads * per_thread + 1))  # every caller saw a distinct count


def test_concurrent_hit_capped_admits_exactly_the_limit(kv):
    admitted: list[bool] = []
    workers = [threading.Thread(target=lambda: admitted.append(kv.hit_capped("c", WINDOW, 5))) for _ in range(20)]
    [w.start() for w in workers]
    [w.join() for w in workers]
    assert admitted.count(True) == 5 and kv.count("c", WINDOW) == 5


@pytest.fixture(params=["memory", "redis"])
def throttle_factory(request, clock):
    shared = MemoryKv(now=clock) if request.param == "memory" else RedisKv(_redis_client(), now=clock)
    return lambda name, attempts, window=WINDOW: AttemptThrottle(attempts, window, name=name, kv=shared)


def test_throttle_matrix(throttle_factory, clock):
    throttle = throttle_factory("t", 2)
    throttle.record("alice")
    assert not throttle.is_blocked("alice")
    throttle.record("alice")
    assert throttle.is_blocked("alice") and not throttle.is_blocked("bob")
    clock.t += WINDOW + 1
    assert not throttle.is_blocked("alice")
    throttle.record("alice")
    throttle.record("alice")
    throttle.reset("alice")
    assert not throttle.is_blocked("alice") and throttle.tracked_keys() == 0


def test_check_and_record_does_not_count_blocked_attempts(throttle_factory, clock):
    throttle = throttle_factory("t", 2)
    assert [throttle.check_and_record("ip") for _ in range(4)] == [True, True, False, False]
    clock.t += WINDOW + 1  # blocked calls did not extend the lockout
    assert throttle.check_and_record("ip")


def test_throttles_with_different_names_do_not_share_counters(throttle_factory):
    first, second = throttle_factory("one", 1), throttle_factory("two", 1)
    first.record("ip")
    assert first.is_blocked("ip") and not second.is_blocked("ip")


def test_challenge_store_matrix(kv, clock):
    store = pk.ChallengeStore(kv, now=clock)
    assert store.consume("a", clock.t + 100) and not store.consume("a", clock.t + 100)
    assert not store.consume("expired", clock.t - 1)


def test_memory_challenge_store_forgets_expired_entries_and_fails_closed_when_full(clock):
    store = pk.ChallengeStore(MemoryKv(max_keys=2, now=clock), now=clock)
    assert store.consume("a", clock.t + 100) and store.consume("b", clock.t + 50)
    assert not store.consume("c", clock.t + 300)  # full of live entries
    clock.t += 60  # "b" has expired
    assert store.consume("c", clock.t + 300)
    clock.t += 100  # "a" expired with its token
    assert store.consume("a", clock.t + 300)


def test_throttle_on_a_shared_kv_needs_a_name(clock):
    with pytest.raises(ValueError):
        AttemptThrottle(3, 60, kv=MemoryKv(now=clock))


def test_memory_kv_is_bounded(clock):
    kv = MemoryKv(max_keys=3, now=clock)
    for index in range(10):
        kv.hit(f"user{index}", WINDOW)
    assert kv.tracked_keys() <= 3


# --- redis specifics ---


def test_every_redis_key_is_prefixed_and_has_a_ttl(clock):
    client = _redis_client()
    kv = RedisKv(client, now=clock)
    kv.hit("a", WINDOW)
    kv.hit_capped("b", WINDOW, 3)
    kv.set_if_absent("c", 90)
    keys = client.keys("*")
    assert sorted(keys) == [f"{KEY_PREFIX}{k}" for k in "abc"]
    assert all(0 < client.ttl(k) <= 91 for k in keys)


def test_replicas_sharing_redis_see_the_same_counters(clock):
    client = _redis_client()
    one = AttemptThrottle(2, WINDOW, name="t", kv=RedisKv(client, now=clock))
    two = AttemptThrottle(2, WINDOW, name="t", kv=RedisKv(client, now=clock))
    one.record("ip")
    two.record("ip")
    assert one.is_blocked("ip") and two.is_blocked("ip")
    two.reset("ip")
    assert not one.is_blocked("ip")


# --- failure policy ---


class BrokenRedis:
    """Stands in for a redis client whose server is gone."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise redis.ConnectionError("down")

        return fail

    def pipeline(self, *args, **kwargs):
        raise redis.TimeoutError("slow")


def test_a_failing_redis_falls_back_to_process_memory_and_still_limits(clock):
    kv = ResilientKv(RedisKv(BrokenRedis(), now=clock), MemoryKv(now=clock), now=clock)
    throttle = AttemptThrottle(2, WINDOW, name="t", kv=kv)
    assert [throttle.check_and_record("ip") for _ in range(3)] == [True, True, False]
    assert throttle.is_blocked("ip")
    assert kv.set_if_absent("jti", 10) and not kv.set_if_absent("jti", 10)
    throttle.reset("ip")
    assert not throttle.is_blocked("ip")
    assert kv.degraded and kv.probe() == "degraded"


def test_redis_errors_are_logged_once_per_minute_without_secrets(clock, caplog):
    kv = ResilientKv(RedisKv(BrokenRedis(), now=clock), MemoryKv(now=clock), now=clock)
    with caplog.at_level(logging.ERROR, logger="auth.audit"):
        for _ in range(5):
            kv.hit("a", WINDOW)
        assert len(caplog.records) == 1
        clock.t += 61
        kv.hit("a", WINDOW)
    assert len(caplog.records) == 2
    assert "TimeoutError" in caplog.text and "down" not in caplog.text


def test_resilient_kv_recovers_when_redis_comes_back(clock):
    client = _redis_client()
    kv = ResilientKv(RedisKv(client, now=clock), MemoryKv(now=clock), now=clock)
    kv._degraded = True
    assert kv.hit("a", WINDOW) == 1 and not kv.degraded and kv.probe() == "ok"


def test_make_kv_is_memory_without_a_url_and_survives_an_unreachable_redis(caplog):
    assert isinstance(make_kv(""), MemoryKv) and make_kv("").probe() == "off"
    with caplog.at_level(logging.ERROR, logger="auth.audit"):
        kv = make_kv("redis://:secret-password@127.0.0.1:1/0")
    assert kv.probe() == "degraded" and kv.hit("a", WINDOW) == 1
    assert "secret-password" not in caplog.text


def test_redis_url_must_have_a_known_scheme(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "http://cache")
    with pytest.raises(ConfigError, match="REDIS_URL"):
        Settings.from_env()
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    assert Settings.from_env().redis_url == "redis://cache:6379/0"


# --- whole app ---


def test_app_with_unreachable_redis_starts_and_still_throttles(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    with TestClient(app_main.create_app("sqlite://")) as client:
        assert client.get("/health").json() == {"status": "ok", "redis": "degraded"}
        client.post("/auth/register", json=CREDS)
        bad = {**CREDS, "password": "wrong-password"}
        for _ in range(5):
            assert client.post("/auth/login", json=bad).status_code == 401
        assert client.post("/auth/login", json=bad).status_code == 429


def test_two_app_instances_share_counters_and_consumed_challenges(monkeypatch):
    server = fakeredis.FakeServer()
    monkeypatch.setattr(app_main, "make_kv", lambda url: RedisKv(_redis_client(server)))
    one, two = app_main.create_app("sqlite://"), app_main.create_app("sqlite://")
    assert one.state.kv is not two.state.kv

    for _ in range(app_main.REAUTH_MAX_FAILURES):
        one.state.reauth_throttle.record("user:1")
    assert two.state.reauth_throttle.is_blocked("user:1")

    token = pk.mint_challenge(pk.LOGIN, b"challenge")
    assert pk.read_challenge(token, pk.LOGIN, one.state.passkey_challenges).challenge == b"challenge"
    with pytest.raises(pk.PasskeyError, match="already used"):
        pk.read_challenge(token, pk.LOGIN, two.state.passkey_challenges)

    with TestClient(two) as client:
        assert client.get("/health").json() == {"status": "ok", "redis": "ok"}
