"""The account-event outbox (written with the change) and the relay to the Redis stream."""

import json
import time
from datetime import timedelta

import fakeredis
import pytest
from sqlalchemy import select

from app.events import EventRelay, add_event
from app.models import AccountEvent, utcnow
from sn_shared.events import ACCOUNT_STREAM
from tests.helpers import CREDS, csrf, register


@pytest.fixture
def stream():
    return fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)


@pytest.fixture
def relay_client(client, stream):
    client.app.state.event_relay = EventRelay(client.app.state.session_factory, lambda: stream)
    return client


def rows(client) -> list[AccountEvent]:
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(AccountEvent).order_by(AccountEvent.id)))


def add_rows(client, count: int) -> None:
    with client.app.state.session_factory() as db:
        for number in range(count):
            add_event(db, "user.renamed", number, {"username": f"n{number}"})
        db.commit()


def delete(client, session):
    return client.request("DELETE", "/auth/me", json={"password": CREDS["password"]}, headers=csrf(session))


def test_outbox_row_rolls_back_with_the_transaction(client):
    with client.app.state.session_factory() as db:
        add_event(db, "user.deleted", 1, {"old_username": "x"})
        db.rollback()
    assert rows(client) == []


def test_delete_writes_a_user_deleted_row_with_only_id_and_old_name(client):
    session = register(client)
    assert delete(client, session).status_code == 204
    (event,) = rows(client)
    assert (event.type, event.user_id) == ("user.deleted", session["id"])
    assert json.loads(event.payload) == {"old_username": "Alice"}
    assert event.published_at is None  # no Redis configured: the row stays


def test_failed_delete_writes_no_event(client):
    session = register(client)
    wrong = client.request("DELETE", "/auth/me", json={"password": "wrong-password"}, headers=csrf(session))
    assert wrong.status_code == 403 and rows(client) == []


def test_delete_is_published_right_after_the_commit(relay_client, stream):
    session = register(relay_client)
    delete(relay_client, session)
    ((_, fields),) = stream.xrange(ACCOUNT_STREAM)
    assert fields["type"] == "user.deleted" and fields["user_id"] == str(session["id"])
    assert json.loads(fields["payload"]) == {"old_username": "Alice"}
    assert rows(relay_client)[0].published_at is not None


def test_relay_publishes_in_id_order_and_marks_rows(client, stream):
    add_rows(client, 3)
    relay = EventRelay(client.app.state.session_factory, lambda: stream)

    assert relay.publish_pending() == 3
    assert [f["user_id"] for _, f in stream.xrange(ACCOUNT_STREAM)] == ["0", "1", "2"]
    assert all(row.published_at for row in rows(client))
    assert relay.publish_pending() == 0  # nothing is published twice


def test_relay_retries_after_a_redis_failure_keeping_order(client, stream, caplog):
    add_rows(client, 3)
    calls = {"n": 0}
    real_xadd = stream.xadd

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] in (2, 3):
            raise ConnectionError("down")
        return real_xadd(*args, **kwargs)

    stream.xadd = flaky
    relay = EventRelay(client.app.state.session_factory, lambda: stream)

    with caplog.at_level("WARNING", logger="sn.events"):
        assert relay.publish_pending() == 0  # swallowed and logged
        relay.publish_pending()  # still failing: the warning is rate limited
    assert sum("not published" in r.message for r in caplog.records) == 1
    assert [row.published_at is not None for row in rows(client)] == [True, False, False]

    assert relay.publish_pending() == 2  # resumes at the first unpublished row
    assert [f["user_id"] for _, f in stream.xrange(ACCOUNT_STREAM)] == ["0", "1", "2"]


def test_relay_without_redis_is_a_noop_and_rows_stay(client):
    add_rows(client, 1)
    relay = EventRelay(client.app.state.session_factory, None)
    relay.start()
    relay.stop()
    assert relay.publish_pending() == 0
    assert rows(client)[0].published_at is None


def test_relay_purges_old_published_rows_only(client, stream):
    with client.app.state.session_factory() as db:
        old, recent, _waiting = (add_event(db, "user.deleted", n, {}) for n in range(3))
        db.flush()
        old.published_at = utcnow() - timedelta(days=8)
        recent.published_at = utcnow() - timedelta(days=1)
        db.commit()
    EventRelay(client.app.state.session_factory, lambda: stream).publish_pending()
    assert [row.user_id for row in rows(client)] == [1, 2]
    assert stream.xlen(ACCOUNT_STREAM) == 1  # only the waiting row was published


def test_relay_thread_publishes_in_the_background(client, stream):
    add_rows(client, 1)
    relay = EventRelay(client.app.state.session_factory, lambda: stream, interval=0.05)
    relay.start()
    deadline = time.time() + 5
    while not stream.xlen(ACCOUNT_STREAM) and time.time() < deadline:
        time.sleep(0.05)
    relay.stop()
    assert stream.xlen(ACCOUNT_STREAM) == 1


def test_app_lifespan_starts_and_stops_the_relay(client):
    assert client.app.state.event_relay.enabled is False  # no REDIS_URL in tests


def test_delete_revokes_tokens_everywhere_and_reserves_the_name(client, revocations):
    session = register(client)
    token = client.cookies.get("sn_token")
    assert delete(client, session).status_code == 204
    assert int(revocations.get(f"sn:minver:{session['id']}")) == 1
    client.cookies.set("sn_token", token, path="/")
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/register", json={"username": "alice", "password": "Correct-Horse-Battery1"}).status_code == 409


def test_a_new_user_never_gets_a_deleted_id(client):
    first = register(client)
    delete(client, first)
    second = register(client, {"username": "bob", "password": "Correct-Horse-Battery1"})
    assert second["id"] > first["id"]
