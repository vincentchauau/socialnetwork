import json

import pytest

ORIGIN = {"Origin": "http://localhost:8080"}


def hdr(cookie, **extra):
    return {**cookie, **extra}


# --- status -----------------------------------------------------------------------------------------------


def test_status_all_up(client, alice):
    assert client.get("/status", headers=alice).json() == {
        "redis": True, "grpc": True, "rabbitmq": True, "kafka": True, "messaging": True,
    }


def test_status_messaging_down(client, fakes, alice):
    fakes.queue.up = False
    body = client.get("/status", headers=alice).json()
    assert body["rabbitmq"] is False and body["kafka"] is True and body["messaging"] is False


def test_status_probe_never_raises_and_times_out(client, fakes, alice, monkeypatch):
    import asyncio

    from app import routes

    async def boom():
        raise RuntimeError("x")

    async def slow():
        await asyncio.sleep(5)

    monkeypatch.setattr(routes, "PROBE_TIMEOUT_SECONDS", 0.05)
    fakes.cache.ping = boom
    fakes.users.ping = slow
    body = client.get("/status", headers=alice).json()
    assert body["redis"] is False and body["grpc"] is False


def test_status_requires_login(client):
    assert client.get("/status").status_code == 401


# --- users (cache aside) ------------------------------------------------------------------------------------


def test_user_miss_then_hit(client, fakes, alice):
    first = client.get("/users/1", headers=alice).json()
    assert first["id"] == "1" and first["name"] == "Alice" and first["source"] == "grpc"
    assert isinstance(first["ms"], int)
    second = client.get("/users/1", headers=alice).json()
    assert second["source"] == "cache" and second["name"] == "Alice"
    assert fakes.users.calls == ["1"]
    assert fakes.cache.ttls["lab:user:1"] == 300


def test_unknown_user(client, alice):
    assert client.get("/users/zz9", headers=alice).json()["name"] == "Unknown"


def test_user_id_validation(client, alice):
    for bad in ("a" * 17, "a-b", "a%20b", "1.5"):
        response = client.get(f"/users/{bad}", headers=alice)
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)


def test_user_grpc_down_is_503(client, fakes, alice):
    fakes.users.up = False
    response = client.get("/users/1", headers=alice)
    assert response.status_code == 503 and "gRPC" in response.json()["detail"]


def test_user_served_from_cache_when_grpc_down(client, fakes, alice):
    client.get("/users/2", headers=alice)
    fakes.users.up = False
    assert client.get("/users/2", headers=alice).json()["source"] == "cache"


def test_user_redis_down_falls_back_to_grpc(client, fakes, alice):
    fakes.cache.up = False
    body = client.get("/users/3", headers=alice).json()
    assert body["name"] == "Charlie" and body["source"] == "grpc"


def test_user_corrupt_cache_entry_is_a_miss(client, fakes, alice):
    fakes.cache.data["lab:user:1"] = "not json"
    assert client.get("/users/1", headers=alice).json()["source"] == "grpc"


def test_clear_cache(client, fakes, alice):
    client.get("/users/1", headers=alice)
    assert client.delete("/users/1/cache", headers=hdr(alice, **ORIGIN)).status_code == 204
    assert "lab:user:1" not in fakes.cache.data
    assert client.get("/users/1", headers=alice).json()["source"] == "grpc"


def test_clear_cache_redis_down_still_204(client, fakes, alice):
    fakes.cache.up = False
    assert client.delete("/users/1/cache", headers=alice).status_code == 204


# --- notifications --------------------------------------------------------------------------------------------


def test_notification_is_stored_and_published(client, fakes, alice):
    response = client.post("/notifications", json={"title": "Hi", "body": "there"}, headers=hdr(alice, **ORIGIN))
    assert response.status_code == 202
    event_id = response.json()["id"]
    assert json.loads(fakes.queue.published[0]) == {"id": event_id, "userId": 1, "title": "Hi", "body": "there"}
    [row] = client.get("/notifications", headers=alice).json()
    assert row["id"] == event_id and row["status"] == "queued" and row["attempts"] == 0
    assert row["processedAt"] is None and row["createdAt"]


def test_notification_rabbit_down_stores_nothing(client, fakes, alice):
    fakes.queue.up = False
    response = client.post("/notifications", json={"title": "Hi", "body": "b"}, headers=alice)
    assert response.status_code == 503 and "RabbitMQ" in response.json()["detail"]
    assert client.get("/notifications", headers=alice).json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "body": "b"},
        {"title": "x" * 81, "body": "b"},
        {"title": "t", "body": "x" * 301},
        {"title": "t", "body": "b", "queue": "other"},
        {"title": "t"},
        {"title": 5, "body": "b"},
    ],
)
def test_notification_validation(client, alice, payload):
    response = client.post("/notifications", json=payload, headers=alice)
    assert response.status_code == 422 and isinstance(response.json()["detail"], str)


def test_notification_rejects_non_json(client, alice):
    response = client.post("/notifications", content=b"title=x", headers=hdr(alice, **{"Content-Type": "text/plain"}))
    assert response.status_code == 422


def test_notifications_are_private_newest_first_and_limited(client, alice, bob):
    for n in range(3):
        client.post("/notifications", json={"title": f"a{n}", "body": "b"}, headers=alice)
    client.post("/notifications", json={"title": "bobs", "body": "b"}, headers=bob)
    titles = [r["title"] for r in client.get("/notifications", headers=alice).json()]
    assert titles == ["a2", "a1", "a0"]
    assert len(client.get("/notifications?limit=2", headers=alice).json()) == 2
    assert [r["title"] for r in client.get("/notifications", headers=bob).json()] == ["bobs"]
    for bad in (0, 101):
        assert client.get(f"/notifications?limit={bad}", headers=alice).status_code == 422


# --- logs ---------------------------------------------------------------------------------------------------


def test_log_is_produced_keyed_by_user(client, fakes, alice, bob):
    response = client.post("/logs", json={"level": "warn", "message": "disk"}, headers=hdr(alice, **ORIGIN))
    assert response.status_code == 202 and response.json() == {"id": 0}
    key, value = fakes.logs.messages[0]
    assert key == "1" and json.loads(value) == {"userId": 1, "level": "warn", "message": "disk"}
    client.post("/logs", json={"level": "info", "message": "bobs"}, headers=bob)
    assert fakes.logs.messages[1][0] == "2"


def test_log_kafka_down(client, fakes, alice):
    fakes.logs.up = False
    response = client.post("/logs", json={"level": "info", "message": "m"}, headers=alice)
    assert response.status_code == 503 and "Kafka" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"level": "debug", "message": "m"},
        {"level": "info", "message": ""},
        {"level": "info", "message": "x" * 201},
        {"level": "info", "message": "m", "topic": "t"},
    ],
)
def test_log_validation(client, alice, payload):
    assert client.post("/logs", json=payload, headers=alice).status_code == 422


def test_logs_list_reads_the_database(client, alice, bob):
    from app import repo
    from datetime import datetime, timezone

    factory = client.app.state.session_factory
    now = datetime.now(timezone.utc)
    repo.store_log(factory, 1, "info", "first", 0, 0, now)
    repo.store_log(factory, 1, "error", "second", 0, 1, now)
    repo.store_log(factory, 2, "info", "bobs", 0, 2, now)
    rows = client.get("/logs", headers=alice).json()
    assert [r["message"] for r in rows] == ["second", "first"]
    assert rows[0]["level"] == "error" and rows[0]["partition"] == 0 and rows[0]["offset"] == 1
    assert set(rows[0]) == {"id", "level", "message", "createdAt", "partition", "offset"}
    assert len(client.get("/logs?limit=1", headers=alice).json()) == 1
    assert client.get("/logs?limit=101", headers=alice).status_code == 422


def test_replay_returns_only_own_messages(client, fakes, alice, bob):
    client.post("/logs", json={"level": "info", "message": "mine"}, headers=alice)
    client.post("/logs", json={"level": "error", "message": "bobs"}, headers=bob)
    client.post("/logs", json={"level": "warn", "message": "mine too"}, headers=alice)
    body = client.get("/logs/replay", headers=alice).json()
    assert body["fromBeginning"] is True
    assert [(m["offset"], m["message"]) for m in body["messages"]] == [(0, "mine"), (2, "mine too")]
    assert set(body["messages"][0]) == {"offset", "partition", "level", "message", "timestamp"}


def test_replay_skips_unreadable_and_respects_limit(client, fakes, alice):
    fakes.logs.messages.append(("1", b"garbage"))
    for n in range(3):
        client.post("/logs", json={"level": "info", "message": f"m{n}"}, headers=alice)
    assert len(client.get("/logs/replay?limit=2", headers=alice).json()["messages"]) == 2
    assert [m["message"] for m in client.get("/logs/replay", headers=alice).json()["messages"]][0] == "m0"
    for bad in (0, 201):
        assert client.get(f"/logs/replay?limit={bad}", headers=alice).status_code == 422


def test_replay_kafka_down(client, fakes, alice):
    fakes.logs.up = False
    assert client.get("/logs/replay", headers=alice).status_code == 503


# --- events / security / limits ---------------------------------------------------------------------------


def test_delete_events_only_removes_callers_rows(client, alice, bob):
    client.post("/notifications", json={"title": "a", "body": "b"}, headers=alice)
    client.post("/notifications", json={"title": "b", "body": "b"}, headers=bob)
    assert client.delete("/events", headers=hdr(alice, **ORIGIN)).status_code == 204
    assert client.get("/notifications", headers=alice).json() == []
    assert len(client.get("/notifications", headers=bob).json()) == 1


def test_writes_reject_foreign_origin(client, alice):
    evil = hdr(alice, Origin="https://evil.example")
    assert client.post("/notifications", json={"title": "a", "body": "b"}, headers=evil).status_code == 403
    assert client.post("/logs", json={"level": "info", "message": "m"}, headers=evil).status_code == 403
    assert client.delete("/events", headers=evil).status_code == 403
    assert client.delete("/users/1/cache", headers=evil).status_code == 403


def test_unauthenticated_writes(client):
    assert client.post("/notifications", json={"title": "a", "body": "b"}).status_code == 401
    assert client.post("/logs", json={"level": "info", "message": "m"}).status_code == 401
    assert client.delete("/events").status_code == 401
    assert client.get("/notifications").status_code == 401
    assert client.get("/logs").status_code == 401
    assert client.get("/logs/replay").status_code == 401
    assert client.get("/users/1").status_code == 401


def test_write_rate_limit_is_per_user_and_counts_deletes(client, alice, bob):
    for _ in range(15):
        assert client.post("/logs", json={"level": "info", "message": "m"}, headers=alice).status_code == 202
    for _ in range(15):
        assert client.delete("/events", headers=alice).status_code == 204
    limited = client.post("/logs", json={"level": "info", "message": "m"}, headers=alice)
    assert limited.status_code == 429 and isinstance(limited.json()["detail"], str)
    assert client.delete("/users/1/cache", headers=alice).status_code == 429
    assert client.post("/logs", json={"level": "info", "message": "m"}, headers=bob).status_code == 202
    assert client.get("/logs", headers=alice).status_code == 200  # reads are not limited


def test_health_needs_no_login(client):
    assert client.get("/health").json() == {"status": "ok"}
