"""RoomStore: bounded memory (rooms, rooms per user), reaping, codes and result retries."""
import random

import pytest

from app import store as store_module
from app.engine import Ability, Faction
from app.rooms import CapacityError, RoomError, RoomNotFound
from app.store import MAX_PERSIST_ATTEMPTS, RoomStore


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(**kw) -> RoomStore:
    return RoomStore(rng=random.Random(5), **kw)


def finish(room) -> None:
    for _ in range(200):
        if room.game.game_over:
            return
        room.game.force()


def test_codes_are_five_uppercase_letters_and_unique():
    store = make()
    codes: set[str] = set()
    for uid in range(1, 40):
        room = store.create(uid, f"u{uid}")
        codes.add(room.code)
        store.leave(room.code, uid)  # keep under the per-user cap
        assert len(room.code) == 5 and room.code.isalpha() and room.code.isupper()
    assert len(codes) >= 38


def test_get_is_case_insensitive_and_require_raises():
    store = make()
    room = store.create(1, "a")
    assert store.get(room.code.lower()) is room
    with pytest.raises(RoomNotFound):
        store.require("ZZZZZ")


def test_custom_code_is_uppercased_and_must_be_free():
    store = make()
    assert store.create(1, "a", code="wolfs").code == "WOLFS"
    with pytest.raises(RoomError, match="WOLFS"):
        store.create(2, "b", code="WOLFS")


def test_max_rooms_is_enforced_then_freed_by_the_reaper():
    clock = FakeClock()
    store = RoomStore(clock=clock, rng=random.Random(1), max_rooms=3)
    for uid in range(1, 4):
        store.create(uid, f"u{uid}")
    with pytest.raises(CapacityError):
        store.create(9, "late")
    clock.now += store_module.IDLE_ROOM_SECONDS
    assert store.create(9, "late") is not None and len(store) == 1


def test_a_user_can_only_hold_a_few_rooms():
    store = make()
    for _ in range(store_module.MAX_ROOMS_PER_USER):
        store.create(1, "a")
    with pytest.raises(RoomError, match="phòng"):
        store.create(1, "a")
    other = store.create(2, "b")
    store.leave(store.rooms_of(1)[0].code, 1)
    store.join(other.code, 1, "a")  # a slot was freed
    with pytest.raises(RoomError):
        store.join(store.create(3, "c").code, 1, "a")


def test_join_a_room_twice_is_rejected_not_counted_against_the_cap():
    store = make()
    room = store.create(1, "a")
    store.join(room.code, 2, "b")
    with pytest.raises(RoomError, match="đã ở trong"):
        store.join(room.code, 2, "b")


def test_leave_deletes_the_room_when_no_human_is_left():
    store = make()
    room = store.create(1, "a")
    store.join(room.code, 2, "b")
    assert store.leave(room.code, 1) is room
    assert store.leave(room.code, 2) is None and store.get(room.code) is None


def test_idle_room_is_reaped_but_activity_postpones_it():
    clock = FakeClock()
    store = RoomStore(clock=clock, rng=random.Random(1))
    room = store.create(1, "a")
    clock.now += store_module.IDLE_ROOM_SECONDS - 1
    assert store.reap() == []
    store.join(room.code, 2, "b")
    clock.now += store_module.IDLE_ROOM_SECONDS - 1
    assert store.reap() == []
    clock.now += 1
    assert store.reap() == [room.code]


def test_finished_rooms_expire_sooner_and_open_sockets_keep_rooms():
    clock = FakeClock()
    connected = {"on": True}
    store = RoomStore(clock=clock, rng=random.Random(1), is_connected=lambda _code: connected["on"])
    room = store.create(1, "a")
    room.start(1)
    finish(room)
    room.touch()
    clock.now += store_module.FINISHED_ROOM_SECONDS
    assert store.reap() == []  # a socket is open
    connected["on"] = False
    assert store.reap() == [room.code]


def test_open_lobbies_lists_only_joinable_listed_rooms_newest_first():
    clock = FakeClock()
    store = RoomStore(clock=clock, rng=random.Random(1))
    old = store.create(1, "a")
    clock.now += 5
    new = store.create(2, "b")
    store.create(3, "c", listed=False)
    started = store.create(4, "d")
    started.start(4)
    full = store.create(5, "e")
    for uid in range(10, 14):
        store.join(full.code, uid, f"f{uid}")
    assert [r.code for r in store.open_lobbies()] == [new.code, old.code]
    assert [r.code for r in store.open_lobbies(limit=1)] == [new.code]


def test_create_validates_timer_count_and_setup():
    store = make()
    with pytest.raises(RoomError):
        store.create(1, "a", timer=3)
    with pytest.raises(RoomError):
        store.create(2, "a", count=4)
    with pytest.raises(RoomError):
        store.create(3, "a", count=41)
    with pytest.raises(Exception):
        store.create(4, "a", roles=[(Faction.VILLAGER, Ability.NONE)] * 5)  # no wolf


def test_unsaved_results_are_retried_a_bounded_number_of_times():
    store = make()
    room = store.create(1, "a")
    room.start(1)
    finish(room)
    record = room.collect_result()
    assert store.unsaved_results() == [record]
    record.attempts = MAX_PERSIST_ATTEMPTS
    assert store.unsaved_results() == []
    record2 = store.create(2, "b")
    record2.start(2)
    finish(record2)
    rec = record2.collect_result()
    assert store.unsaved_results() == [rec]
    rec.saved = True
    assert store.unsaved_results() == []


def test_results_of_deleted_rooms_are_kept_until_saved():
    store = make()
    room = store.create(1, "a")
    room.start(1)
    finish(room)
    record = room.collect_result()
    store.delete(room.code)
    assert store.unsaved_results() == [record]
    record.inflight = True
    assert store.unsaved_results() == []
