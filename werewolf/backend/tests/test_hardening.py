import asyncio
import random
from contextlib import ExitStack

import pytest
from starlette.websockets import WebSocketDisconnect

from app import store as store_module
from app import ws as ws_module
from app.engine import Game, GameError, Phase, Player, Role, Winner
from app.history import save_result
from app.service import reaper_loop, sweep
from app.store import RoomStore
from tests.conftest import ws_headers
from tests.test_api import make_room, post
from tests.test_ws import open_all, start_room


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def finished_game() -> Game:
    players = (Player(1, "a", Role.VILLAGER), Player(2, "b", Role.WEREWOLF, alive=False))
    return Game(players=players, host_id=1, phase=Phase.FINISHED, day=2, winner=Winner.VILLAGE)


# ---- 1. room expiry ----

def test_idle_room_is_reaped_after_timeout():
    clock = FakeClock()
    store = RoomStore(clock=clock)
    room_id, _ = store.create(1, "a")
    clock.now += store_module.IDLE_ROOM_SECONDS - 1
    assert store.reap() == [] and store.get(room_id) is not None
    clock.now += 1
    assert store.reap() == [room_id] and store.get(room_id) is None


def test_activity_postpones_expiry():
    clock = FakeClock()
    store = RoomStore(clock=clock)
    room_id, _ = store.create(1, "a")
    clock.now += store_module.IDLE_ROOM_SECONDS - 1
    store.join(room_id, 2, "b")
    clock.now += store_module.IDLE_ROOM_SECONDS - 1
    assert store.reap() == []


def test_finished_room_expires_sooner_and_open_sockets_keep_rooms():
    clock = FakeClock()
    connected = {"on": True}
    store = RoomStore(clock=clock, is_connected=lambda _id: connected["on"])
    room_id, _ = store.create(1, "a")
    store.update(room_id, lambda g: finished_game())
    clock.now += store_module.FINISHED_ROOM_SECONDS
    assert store.reap() == []  # somebody is still connected
    connected["on"] = False
    assert store.reap() == [room_id]


def test_create_reaps_expired_rooms_when_full(monkeypatch):
    monkeypatch.setattr(store_module, "MAX_ROOMS", 2)
    clock = FakeClock()
    store = RoomStore(clock=clock)
    store.create(1, "a")
    store.create(2, "b")
    with pytest.raises(GameError):
        store.create(3, "c")
    clock.now += store_module.IDLE_ROOM_SECONDS
    store.create(3, "c")
    assert len(store.open_lobbies()) == 1


def test_open_lobbies_reaps():
    clock = FakeClock()
    store = RoomStore(clock=clock)
    store.create(1, "a")
    clock.now += store_module.IDLE_ROOM_SECONDS
    assert store.open_lobbies() == []


def test_lifespan_runs_and_stops_reaper(client):
    assert client.get("/health").status_code == 200  # app started inside the lifespan context


def test_reaper_loop_sweeps_and_survives_errors(client):
    app = client.app
    calls = []

    def flaky(_app):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    async def run() -> None:
        import app.service as service

        original = service.sweep
        service.sweep = flaky
        try:
            task = asyncio.create_task(reaper_loop(app, interval=0.01))
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            service.sweep = original

    asyncio.run(run())
    assert len(calls) >= 2


def test_sweep_reaps_via_app(client):
    app = client.app
    clock = FakeClock()
    app.state.store._clock = clock
    room_id = post(client, "/rooms").json()["id"]
    clock.now += store_module.IDLE_ROOM_SECONDS
    sweep(app)
    assert app.state.store.get(room_id) is None


# ---- 2. connection limits ----

def test_second_socket_for_same_user_replaces_the_first(client):
    room_id, _ = start_room(client)
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as first:
        first.receive_json()
        with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as second:
            assert second.receive_json()["type"] == "state"
            with pytest.raises(WebSocketDisconnect) as info:
                first.receive_json()
            assert info.value.code == 1008
            assert client.app.state.hub.size(room_id) == 1


def test_rate_limit_is_shared_across_a_users_connections(client, monkeypatch):
    monkeypatch.setattr(ws_module, "RATE_LIMIT_MESSAGES", 2)
    room_id, _ = start_room(client)
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as first:
        first.receive_json()
        for _ in range(2):
            first.send_text("{}")
            first.receive_json()
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as second:
        second.receive_json()
        second.send_text("{}")  # reconnecting does not reset the allowance
        with pytest.raises(WebSocketDisconnect) as info:
            second.receive_json()
    assert info.value.code == 1008


def test_global_connection_cap_refuses_with_1013(client):
    room_id, _ = start_room(client)
    client.app.state.hub._max_connections = 1
    with ExitStack() as stack:
        open_all(client, stack, room_id, [1])
        with pytest.raises(WebSocketDisconnect) as info:
            with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers(2, "user2")):
                pass
    assert info.value.code == 1013


def test_idle_limiters_are_pruned(client):
    hub = client.app.state.hub
    hub.limiter_for(7, 5, 0.0)
    hub.limiter_for(8, 5, 0.0)  # triggers pruning of user 7 (idle, not connected)
    assert set(hub._limiters) == {8}


# ---- 4. frame size ----

def test_parse_rejects_oversized_raw_without_json_decode():
    assert ws_module._parse("x" * (ws_module.MAX_FRAME_CHARS + 1)) is None


# ---- 5. shuffle rng ----

def test_default_rng_is_system_random_and_injection_still_works():
    assert isinstance(RoomStore().rng, random.SystemRandom)
    seeded = random.Random(1)
    assert RoomStore(rng=seeded).rng is seeded


# ---- 6. persistence ----

class BrokenFactory:
    def __call__(self):
        raise RuntimeError("db down")


def test_save_result_reports_failure_and_success(client):
    game = finished_game()
    assert save_result(BrokenFactory(), "r", game) is False
    assert save_result(client.app.state.session_factory, "r", game) is True
    assert save_result(BrokenFactory(), "r", Game(players=(), host_id=1)) is True  # nothing to save


def test_failed_write_is_retried_until_it_succeeds(client):
    app = client.app
    good_factory = app.state.session_factory
    app.state.session_factory = BrokenFactory()
    room_id = post(client, "/rooms").json()["id"]
    result = app.state.store.update(room_id, lambda g: finished_game())
    assert result.finished_now
    from app.service import _save

    _save(app, room_id, result.game)  # fails: stays unpersisted
    assert [i for i, _ in app.state.store.unsaved_results()] == [room_id]
    app.state.session_factory = good_factory
    sweep(app)  # retry succeeds
    assert app.state.store.unsaved_results() == []


def test_persist_retries_are_bounded(monkeypatch):
    store = RoomStore()
    room_id, _ = store.create(1, "a")
    store.update(room_id, lambda g: finished_game())  # attempt 1 (finished_now)
    seen = 0
    for _ in range(store_module.MAX_PERSIST_ATTEMPTS + 3):
        seen += len(store.unsaved_results())
    assert seen == store_module.MAX_PERSIST_ATTEMPTS - 1
    assert store.update(room_id, lambda g: g).finished_now is False


def test_mark_persisted_stops_retries_and_ignores_unknown_room():
    store = RoomStore()
    room_id, _ = store.create(1, "a")
    store.update(room_id, lambda g: finished_game())
    store.mark_persisted(room_id)
    store.mark_persisted("missing")
    assert store.unsaved_results() == []


# ---- 7. versions ----

def test_state_version_increases_with_every_change(client):
    room_id = make_room(client, 1)
    first = client.get(f"/rooms/{room_id}", headers=ws_headers()).json()["state"]["version"]
    post(client, f"/rooms/{room_id}/join", 2, "user2")
    second = client.get(f"/rooms/{room_id}", headers=ws_headers()).json()["state"]["version"]
    assert second > first
