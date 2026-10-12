from fastapi.testclient import TestClient

from app.main import create_app
from app.throttle import AttemptThrottle
from tests.helpers import CREDS


def test_blocks_after_max_attempts():
    clock = [0.0]
    throttle = AttemptThrottle(max_attempts=2, window_seconds=60, now=lambda: clock[0])

    throttle.record("alice")
    assert not throttle.is_blocked("alice")
    throttle.record("alice")
    assert throttle.is_blocked("alice")
    assert not throttle.is_blocked("bob")


def test_attempts_expire_after_window():
    clock = [0.0]
    throttle = AttemptThrottle(max_attempts=1, window_seconds=60, now=lambda: clock[0])
    throttle.record("alice")
    clock[0] = 61.0
    assert not throttle.is_blocked("alice")


def test_reset_clears_attempts():
    throttle = AttemptThrottle(max_attempts=1, window_seconds=60)
    throttle.record("alice")
    throttle.reset("alice")
    assert not throttle.is_blocked("alice")


def test_memory_is_bounded_by_max_keys():
    throttle = AttemptThrottle(max_attempts=5, window_seconds=60, max_keys=3)
    for index in range(10):
        throttle.record(f"user{index}")
    assert throttle.tracked_keys() <= 3


def test_login_returns_429_after_repeated_failures(client):
    client.post("/auth/register", json=CREDS)
    bad = {**CREDS, "password": "wrong-password"}
    for _ in range(5):
        assert client.post("/auth/login", json=bad).status_code == 401

    assert client.post("/auth/login", json=bad).status_code == 429
    assert client.post("/auth/login", json=CREDS).status_code == 429


def test_attacker_cannot_lock_out_victim_from_another_address(client):
    client.post("/auth/register", json=CREDS)
    attacker = TestClient(client.app, client=("203.0.113.9", 4000))
    bad = {**CREDS, "password": "wrong-password"}
    for _ in range(6):
        attacker.post("/auth/login", json=bad)

    assert attacker.post("/auth/login", json=bad).status_code == 429
    assert client.post("/auth/login", json=CREDS).status_code == 200


def test_one_address_spraying_many_usernames_gets_blocked(client):
    codes = [
        client.post("/auth/login", json={"username": f"user{i}", "password": "wrong-password"}).status_code
        for i in range(25)
    ]
    assert codes[0] == 401
    assert codes[-1] == 429


def test_register_is_throttled_per_address(client):
    codes = [
        client.post("/auth/register", json={"username": f"user{i}", "password": "s3cret-pass"}).status_code
        for i in range(12)
    ]
    assert codes[0] == 201
    assert codes[-1] == 429


def test_account_is_locked_across_addresses_at_four_times_the_limit(client):
    client.post("/auth/register", json=CREDS)
    bad = {**CREDS, "password": "wrong-password"}
    codes = []
    for index in range(22):
        attacker = TestClient(client.app, client=(f"198.51.100.{index}", 4000))
        codes.append(attacker.post("/auth/login", json=bad).status_code)
    assert codes[:20] == [401] * 20
    assert codes[20:] == [429, 429]
    # The real owner is locked out too (documented trade-off of an account-wide cap)...
    assert client.post("/auth/login", json=CREDS).status_code == 429


def test_successful_login_clears_the_per_address_counter(client):
    client.post("/auth/register", json=CREDS)
    bad = {**CREDS, "password": "wrong-password"}
    for _ in range(4):
        client.post("/auth/login", json=bad)
    assert client.post("/auth/login", json=CREDS).status_code == 200
    for _ in range(4):
        assert client.post("/auth/login", json=bad).status_code == 401
