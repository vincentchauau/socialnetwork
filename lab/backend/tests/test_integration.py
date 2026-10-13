"""Runs against the REAL stack (Redis, lab-user, RabbitMQ, Kafka, lab-worker); skipped unless LAB_INTEGRATION=1.

    LAB_INTEGRATION=1 LAB_BASE_URL=http://localhost:8080 LAB_COOKIE='<sn auth cookie name>=<jwt>' \
        python -m pytest tests/test_integration.py -q -p no:cacheprovider

Take the cookie from the browser (DevTools > Application > Cookies) after signing in. `docker compose` must run with
COMPOSE_PROFILES=mail-dev,messaging so that RabbitMQ, Kafka and lab-worker are up.
"""

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("LAB_INTEGRATION") != "1", reason="set LAB_INTEGRATION=1 to run")

BASE = os.environ.get("LAB_BASE_URL", "http://localhost:8080").rstrip("/")
ORIGIN = os.environ.get("LAB_ORIGIN", BASE)


@pytest.fixture(scope="module")
def http():
    cookie_name, _, value = os.environ["LAB_COOKIE"].partition("=")
    with httpx.Client(
        base_url=f"{BASE}/api/lab", cookies={cookie_name: value}, headers={"Origin": ORIGIN}, timeout=10
    ) as client:
        client.delete("/events")
        yield client
        client.delete("/events")


def wait_for(fetch, predicate, seconds=15.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = fetch()
        if predicate(value):
            return value
        time.sleep(0.5)
    raise AssertionError(f"condition not met within {seconds}s; last value: {value!r}")


def test_status_all_up(http):
    assert http.get("/status").json() == {
        "redis": True, "grpc": True, "rabbitmq": True, "kafka": True, "messaging": True,
    }


def test_grpc_with_redis_cache_aside(http):
    http.delete("/users/2/cache")
    assert http.get("/users/2").json()["source"] == "grpc"
    hit = http.get("/users/2").json()
    assert hit["name"] == "Bob" and hit["source"] == "cache"
    assert http.get("/users/99").json()["name"] == "Unknown"


def test_rabbitmq_work_queue_done_and_dead_letter(http):
    ok = http.post("/notifications", json={"title": "integration ok", "body": "b"}).json()["id"]
    bad = http.post("/notifications", json={"title": "[fail] integration", "body": "b"}).json()["id"]

    def rows():
        return {row["id"]: row for row in http.get("/notifications").json()}

    done = wait_for(rows, lambda r: r[ok]["status"] == "done")
    assert done[ok]["processedAt"] is not None
    dead = wait_for(rows, lambda r: r[bad]["status"] == "dead", seconds=30)
    assert dead[bad]["attempts"] == 3


def test_kafka_log_is_stored_and_replayed(http):
    http.post("/logs", json={"level": "warn", "message": "integration log"})

    def stored():
        return http.get("/logs").json()

    rows = wait_for(stored, lambda r: any(x["message"] == "integration log" for x in r))
    assert rows[0]["partition"] == 0 and isinstance(rows[0]["offset"], int)
    replay = http.get("/logs/replay").json()
    assert replay["fromBeginning"] is True
    assert any(m["message"] == "integration log" for m in replay["messages"])
