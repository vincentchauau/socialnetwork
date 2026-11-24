"""Hub efficiency/eviction and the per-user limiter, with fake sockets and a fake clock."""
import asyncio
import json

import pytest

from api.werewolf.hub import GameHub, dumps
from api.werewolf.limits import RULES, UserLimits
from sn_shared.limits import SlidingWindow


class FakeSocket:
    def __init__(self, slow: bool = False, broken: bool = False) -> None:
        self.sent: list[str] = []
        self.closed: int | None = None
        self.accepted = False
        self.slow, self.broken = slow, broken

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.slow:
            await asyncio.sleep(10)
        if self.broken:
            raise RuntimeError("gone")
        self.sent.append(text)

    async def close(self, code: int = 1000) -> None:
        self.closed = code


def run(coro):
    return asyncio.run(coro)


def test_one_state_per_user_and_unchanged_frames_are_skipped():
    hub = GameHub()
    calls = []

    def state_for(uid):
        calls.append(uid)
        return {"v": uid}

    async def scenario():
        a, b = FakeSocket(), FakeSocket()
        await hub.join("R", a, 1)
        await hub.join("R", b, 2)
        await hub.broadcast("R", state_for)
        await hub.broadcast("R", state_for)  # nothing changed: nothing sent
        return a, b

    a, b = run(scenario())
    assert sorted(calls) == [1, 1, 2, 2]  # one view computed per user per broadcast
    assert len(a.sent) == len(b.sent) == 1
    assert json.loads(a.sent[0]) == {"type": "state", "state": {"v": 1}}


def test_changed_state_is_sent_again():
    hub = GameHub()
    box = {"n": 0}

    async def scenario():
        s = FakeSocket()
        await hub.join("R", s, 1)
        for n in (1, 1, 2):
            box["n"] = n
            await hub.broadcast("R", lambda uid: {"n": box["n"]})
        return s

    assert len(run(scenario()).sent) == 2


def test_users_without_a_seat_are_disconnected():
    hub = GameHub()

    async def scenario():
        gone, kept = FakeSocket(), FakeSocket()
        await hub.join("R", gone, 1)
        await hub.join("R", kept, 2)
        await hub.broadcast("R", lambda uid: None if uid == 1 else {"ok": True})
        return gone, kept

    gone, kept = run(scenario())
    assert gone.closed == 1008 and gone.sent == [] and kept.sent
    assert hub.users("R") == {2}


def test_a_dead_or_slow_socket_is_dropped_without_blocking_the_others():
    hub = GameHub(send_timeout=0.05)

    async def scenario():
        slow, broken, fine = FakeSocket(slow=True), FakeSocket(broken=True), FakeSocket()
        for uid, s in enumerate((slow, broken, fine), 1):
            await hub.join("R", s, uid)
        await hub.broadcast("R", lambda uid: {"x": 1})
        return fine

    fine = run(scenario())
    assert fine.sent and hub.users("R") == {3}


def test_chat_goes_only_to_the_recipients():
    hub = GameHub()

    async def scenario():
        socks = {uid: FakeSocket() for uid in (1, 2, 3)}
        for uid, s in socks.items():
            await hub.join("R", s, uid)
        await hub.send_chat("R", [1, 3], {"text": "psst"})
        return socks

    socks = run(scenario())
    assert [bool(s.sent) for s in socks.values()] == [True, False, True]
    assert json.loads(socks[1].sent[0]) == {"type": "chat", "message": {"text": "psst"}}


def test_join_replaces_a_users_older_socket_and_close_room_closes_all():
    hub = GameHub()

    async def scenario():
        old, new, other = FakeSocket(), FakeSocket(), FakeSocket()
        await hub.join("R", old, 1)
        await hub.join("R", new, 1)
        await hub.join("R", other, 2)
        assert old.closed == 1008 and hub.size("R") == 2 and hub.total() == 2
        await hub.close_room("R")
        return new, other

    new, other = run(scenario())
    assert new.closed == other.closed == 1001 and hub.size("R") == 0
    hub.leave("R", new)  # leaving twice is harmless


def test_capacity_and_error_frames():
    hub = GameHub(max_connections=1)

    async def scenario():
        s = FakeSocket()
        assert not hub.is_full()
        await hub.join("R", s, 1)
        assert hub.is_full()
        await hub.send_error(s, "nope")
        return s

    assert json.loads(run(scenario()).sent[0]) == {"type": "error", "error": "nope"}


def test_dumps_is_compact_and_keeps_unicode():
    assert dumps({"a": "Sói"}) == '{"a":"Sói"}'


# ---- limiter ----
class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def test_sliding_window_limiter():
    clock = Clock()
    limiter = SlidingWindow(2, 10.0, clock)
    assert limiter.idle()
    assert limiter.allow() and limiter.allow() and not limiter.allow()
    assert not limiter.idle()
    clock.now = 10.5
    assert limiter.allow() and limiter.idle() is False
    clock.now = 100
    assert limiter.idle()


def test_user_limits_are_per_kind_and_per_user_and_pruned():
    clock = Clock()
    limits = UserLimits(clock, {"chat": (1, 5.0), "rest": (2, 5.0)})
    assert limits.allow("chat", 1) and not limits.allow("chat", 1)
    assert limits.allow("chat", 2) and limits.allow("rest", 1)  # other user / other kind: own budget
    assert limits.size() == 3
    clock.now = 100
    limits.prune()
    assert limits.size() == 0


def test_user_limits_prune_themselves_when_the_table_grows():
    clock = Clock()
    limits = UserLimits(clock, {"rest": (1, 1.0)})
    for uid in range(1100):
        clock.now += 2  # every earlier entry is idle by the next call
        limits.allow("rest", uid)
    assert limits.size() < 1100


def test_default_rules_cover_every_kind_in_use():
    assert {"rest", "create", "join", "chat", "ws"} <= set(RULES)
    with pytest.raises(KeyError):
        UserLimits().allow("unknown", 1)
