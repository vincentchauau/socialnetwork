import json
import sys
import types

import fakeredis
import pytest

from sn_shared import events
from sn_shared.events import ACCOUNT_STREAM, DEAD_STREAM, AccountConsumer, start_account_consumer

MODULE = "fake_account_events"


class FakeDb:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)


@pytest.fixture
def calls():
    return []


@pytest.fixture
def handlers(calls):
    """Installs a fake `app.account_events`-like module; `module.fail` makes the handlers raise."""
    module = types.ModuleType(MODULE)
    module.fail = False

    def on_user_deleted(db, user_id):
        calls.append(("deleted", user_id))
        if module.fail:
            raise RuntimeError("boom")

    def on_user_renamed(db, user_id, new_username):
        calls.append(("renamed", user_id, new_username))

    module.on_user_deleted, module.on_user_renamed = on_user_deleted, on_user_renamed
    sys.modules[MODULE] = module
    yield module
    sys.modules.pop(MODULE, None)


def publish(client, kind="user.deleted", user_id=7, payload="{}"):
    return client.xadd(ACCOUNT_STREAM, {"event_id": "1", "type": kind, "user_id": str(user_id), "payload": payload})


def consumer(client, name="chat", log=None, **kwargs):
    kwargs.setdefault("handlers_module", MODULE)
    c = AccountConsumer(name, lambda: FakeDb(log if log is not None else []), client, **kwargs)
    c.ensure_group()
    return c


def pending(client, group):
    return client.xpending(ACCOUNT_STREAM, group)["pending"]


def test_each_group_gets_every_event_and_acks(redis_client, handlers, calls):
    chat, photos = consumer(redis_client, "chat"), consumer(redis_client, "photos")
    publish(redis_client, "user.deleted", 7)
    publish(redis_client, "user.renamed", 8, '{"username":"bob","old_username":"alice"}')

    assert chat.process_once() == 2 and photos.process_once() == 2

    assert calls.count(("deleted", 7)) == 2 and calls.count(("renamed", 8, "bob")) == 2
    assert pending(redis_client, "chat") == 0 and pending(redis_client, "photos") == 0
    assert chat.process_once() == 0


def test_handler_session_is_committed_on_success(redis_client, handlers):
    log = []
    c = consumer(redis_client, log=log)
    publish(redis_client)
    c.process_once()
    assert log == ["commit"]


def test_failed_handler_rolls_back_and_is_redelivered(redis_client, handlers, calls):
    log = []
    c = consumer(redis_client, log=log, reclaim_idle_ms=0)
    handlers.fail = True
    publish(redis_client)

    c.process_once()
    assert log == ["rollback"] and pending(redis_client, "chat") == 1

    handlers.fail = False
    c.process_once()  # reclaimed (idle 0) and now succeeds
    assert pending(redis_client, "chat") == 0
    assert [call[0] for call in calls] == ["deleted", "deleted"]


def test_idle_threshold_keeps_fresh_pending_entries_alone(redis_client, handlers, calls):
    c = consumer(redis_client)  # default 60 s
    handlers.fail = True
    publish(redis_client)
    c.process_once()
    c.process_once()
    assert len(calls) == 1 and pending(redis_client, "chat") == 1


def test_dead_letter_after_five_deliveries(redis_client, handlers, calls):
    c = consumer(redis_client, reclaim_idle_ms=0)
    handlers.fail = True
    message_id = publish(redis_client, "user.deleted", 9)

    for _ in range(5):
        c.process_once()

    assert len(calls) == 5 and pending(redis_client, "chat") == 0
    (dead_id, fields), = redis_client.xrange(DEAD_STREAM)
    assert fields["error"] == "RuntimeError" and fields["app"] == "chat"
    assert fields["original_id"] == message_id and fields["user_id"] == "9"


def test_new_group_catches_up_on_history(redis_client, handlers, calls):
    publish(redis_client, "user.deleted", 1)
    publish(redis_client, "user.deleted", 2)

    late = consumer(redis_client, "market")
    late.process_once()

    assert calls == [("deleted", 1), ("deleted", 2)]


def test_missing_module_skips_and_acks(redis_client, caplog):
    c = consumer(redis_client, handlers_module="no_such_module_here")
    publish(redis_client)
    publish(redis_client)

    with caplog.at_level("WARNING", logger="sn.events"):
        c.process_once()

    assert pending(redis_client, "chat") == 0
    assert sum("not found" in r.message for r in caplog.records) == 1  # warned once


def test_missing_handler_function_unknown_type_and_malformed_are_acked(redis_client, handlers, calls):
    del handlers.on_user_renamed
    c = consumer(redis_client)
    publish(redis_client, "user.renamed", 1, '{"username":"x"}')
    publish(redis_client, "user.exploded", 2)
    redis_client.xadd(ACCOUNT_STREAM, {"type": "user.deleted", "user_id": "abc"})
    publish(redis_client, "user.renamed", 3, "not json")

    c.process_once()

    assert calls == [] and pending(redis_client, "chat") == 0


def test_import_error_inside_the_handlers_module_is_a_failure_not_a_skip(redis_client, monkeypatch):
    broken = types.ModuleType("x")
    monkeypatch.setattr(
        events.importlib, "import_module", lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name="sqlalchemyy"))
    )
    c = consumer(redis_client)
    publish(redis_client)
    c.process_once()
    assert pending(redis_client, "chat") == 1 and broken


def test_noop_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    handle = start_account_consumer("chat", lambda: FakeDb([]))
    handle.stop()
    handle = start_account_consumer("chat", lambda: FakeDb([]), redis_url="")
    handle.stop()


def test_thread_consumes_and_stops(redis_client, handlers, calls):
    handle = start_account_consumer("chat", lambda: FakeDb([]), client=redis_client, poll_ms=50)
    handle._module_name = MODULE  # noqa: SLF001 - the default module name is not importable here
    publish(redis_client, "user.deleted", 5)
    import time

    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.05)
    handle.stop()
    assert ("deleted", 5) in calls


def renamed(client, user_id, name, seq=None):
    payload = {"username": name, "old_username": "x", **({"seq": seq} if seq is not None else {})}
    return publish(client, "user.renamed", user_id, json.dumps(payload))


def test_stale_rename_is_skipped_and_newer_accepted(redis_client, handlers, calls):
    c = consumer(redis_client)
    renamed(redis_client, 4, "second", seq=20)
    renamed(redis_client, 4, "first", seq=10)  # late, older
    renamed(redis_client, 4, "same", seq=20)  # duplicate
    renamed(redis_client, 4, "third", seq=30)
    c.process_once()
    assert [call[2] for call in calls] == ["second", "third"]
    assert pending(redis_client, "chat") == 0
    assert redis_client.get("sn:events:rename-seq:chat:4") == "30"
    assert 0 < redis_client.ttl("sn:events:rename-seq:chat:4") <= 30 * 86400


def test_rename_marks_are_per_app_and_user(redis_client, handlers, calls):
    renamed(redis_client, 1, "a", seq=5)
    renamed(redis_client, 2, "b", seq=1)
    consumer(redis_client, "chat").process_once()
    consumer(redis_client, "photos").process_once()
    assert len(calls) == 4


def test_legacy_rename_without_seq_is_always_processed(redis_client, handlers, calls):
    c = consumer(redis_client)
    renamed(redis_client, 4, "one")
    renamed(redis_client, 4, "two")
    c.process_once()
    assert [call[2] for call in calls] == ["one", "two"]
    assert redis_client.get("sn:events:rename-seq:chat:4") is None


def test_failed_rename_does_not_raise_the_mark(redis_client, handlers, calls):
    c = consumer(redis_client, reclaim_idle_ms=0)

    def boom(db, user_id, name):
        raise RuntimeError("x")

    handlers.on_user_renamed = boom
    renamed(redis_client, 4, "n", seq=9)
    c.process_once()
    assert redis_client.get("sn:events:rename-seq:chat:4") is None and pending(redis_client, "chat") == 1


def test_created_event_reaches_an_app_that_handles_it_and_is_skipped_by_one_that_does_not(redis_client, handlers, calls):
    handlers.on_user_created = lambda db, user_id, username, kind, body: calls.append(("created", user_id, username, kind))
    publish(redis_client, "user.created", 9, '{"username":"Lan_Nguyen","kind":"virtual"}')
    publish(redis_client, "user.created", 10, '{"kind":"virtual"}')  # no name: malformed, acknowledged
    c = consumer(redis_client)
    c.process_once()
    assert calls == [("created", 9, "Lan_Nguyen", "virtual")] and pending(redis_client, "chat") == 0
    del handlers.on_user_created  # an app without the handler: skipped and acknowledged, the stream never stalls
    publish(redis_client, "user.created", 11, '{"username":"x"}')
    c.process_once()
    assert pending(redis_client, "chat") == 0
