"""Persistence, the timer tick loop, the reaper and the lifespan wiring."""
import asyncio
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main as main_module
from app import service
from app.main import create_app
from app.models import GamePlayer, GameResult
from app.store import MAX_PERSIST_ATTEMPTS
from tests.test_api import get, make_room, name_of, play_out, post, seats, start
from tests.test_ws import next_frame, open_state


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def timed(request):
    clock = FakeClock()
    with TestClient(create_app("sqlite://", clock=clock)) as test_client:
        yield test_client, clock


def stored(client):
    with client.app.state.session_factory() as session:
        return session.scalars(select(GameResult)).unique().all(), session.scalars(select(GamePlayer)).all()


def test_a_finished_game_is_stored_once_per_game_with_humans_only(client):
    code = make_room(client, 2)
    start(client, code)
    play_out(client, code)
    play_out(client, code)  # reading the state again must not store it again
    results, players = stored(client)
    assert len(results) == 1 and results[0].room_id == code and results[0].size == 5
    assert sorted(p.username for p in players) == ["alice", "user2"]
    assert all(p.faction and p.outcome in ("won", "lost", "draw") and p.user_id > 0 for p in players)
    post(client, f"/rooms/{code}/rematch")
    play_out(client, code)
    assert len(stored(client)[0]) == 2


def test_the_last_human_walking_away_still_gets_the_finished_game_stored(client):
    code = make_room(client, seats=seats(7))
    start(client, code)
    post(client, f"/rooms/{code}/leave")  # the only human leaves: the bots play the game out, the room is gone
    results, players = stored(client)
    assert get(client, f"/rooms/{code}").status_code == 404
    assert len(results) == 1 and [p.username for p in players] == ["alice"]
    assert players[0].outcome in ("won", "lost", "draw")


def test_a_failed_write_is_retried_by_the_reaper_a_bounded_number_of_times(client, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "save_record", lambda factory, record: calls.append(record) or False)
    code = make_room(client)
    start(client, code)
    play_out(client, code)
    assert len(calls) == 1
    for _ in range(MAX_PERSIST_ATTEMPTS + 3):
        client.portal.call(service.sweep, client.app)
    assert len(calls) == MAX_PERSIST_ATTEMPTS  # then it gives up instead of retrying forever
    assert client.app.state.store.unsaved_results() == []


def test_a_retry_that_succeeds_clears_the_record(client, monkeypatch):
    real = service.save_record
    monkeypatch.setattr(service, "save_record", lambda factory, record: False)
    code = make_room(client)
    start(client, code)
    play_out(client, code)
    monkeypatch.setattr(service, "save_record", real)
    client.portal.call(service.sweep, client.app)
    assert len(stored(client)[0]) == 1
    client.portal.call(service.sweep, client.app)
    assert len(stored(client)[0]) == 1 and client.app.state.store.unsaved_results() == []


def test_a_record_being_written_is_not_written_twice(client):
    code = make_room(client)
    start(client, code)
    room = client.app.state.store.get(code)
    room.game.game_over = True
    record = room.collect_result()
    record.inflight = True
    client.portal.call(service.persist, client.app, room)
    assert stored(client)[0] == []


def test_tick_forces_an_expired_turn_for_rooms_with_a_socket(timed):
    client, clock = timed
    code = make_room(client, seats=seats(7), timerSeconds=30)
    start(client, code)
    before = client.app.state.store.get(code).game.night
    assert client.portal.call(service.tick_once, client.app) == 0  # nobody connected: no tick
    with ExitStack() as stack:
        socket, state = open_state(client, stack, code)
        assert state["game"]["timer"]["total"] in (30, 60)
        assert client.portal.call(service.tick_once, client.app) == 0  # time has not run out
        clock.now += 31
        assert client.portal.call(service.tick_once, client.app) == 1
        pushed = next_frame(socket, "state")["state"]
        assert pushed["game"]["phase"] != "night" or pushed["game"]["night"] > before


def test_tick_skips_finished_and_untimed_games(timed):
    client, clock = timed
    code = make_room(client, seats=seats(7))
    start(client, code)
    clock.now += 10_000
    with ExitStack() as stack:
        open_state(client, stack, code)
        assert client.portal.call(service.tick_once, client.app) == 0  # no timer
        play_out(client, code)
        assert client.portal.call(service.tick_once, client.app) == 0  # over


def test_sweep_reaps_idle_rooms(timed):
    client, clock = timed
    code = make_room(client)
    clock.now += 10_000
    client.portal.call(service.sweep, client.app)
    assert get(client, f"/rooms/{code}").status_code == 404


def test_background_steps_survive_errors():
    calls = []

    async def failing(app):
        calls.append(1)
        raise RuntimeError("boom")

    async def run():
        task = asyncio.create_task(service._forever(None, 0.001, failing))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert len(calls) >= 2  # an error is logged, the loop keeps going


def test_lifespan_starts_and_cancels_both_loops(monkeypatch):
    events = []

    def fake(name):
        async def loop(app):
            events.append(f"{name} start")
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                events.append(f"{name} cancelled")
                raise

        return loop

    monkeypatch.setattr(main_module, "reaper_loop", fake("reaper"))
    monkeypatch.setattr(main_module, "tick_loop", fake("tick"))
    with TestClient(create_app("sqlite://")):
        pass
    assert sorted(events) == ["reaper cancelled", "reaper start", "tick cancelled", "tick start"]
