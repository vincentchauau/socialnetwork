"""A game goes on after a restart: its room is saved after every change and put back when the server starts."""

import io
import pickle

import pytest
from sqlalchemy import select

from api.werewolf import snapshots
from api.werewolf.models import LIVE, Game
from api.werewolf.store import RoomStore
from tests.werewolf.conftest import make_client
from tests.werewolf.test_api import get, make_room, play_out, post, start


def state_of(client, code, user=1, name="alice"):
    return get(client, f"/rooms/{code}", user, name).json()["state"]


def codes_saved(client):
    with client.app.state.session_factory() as db:
        return set(db.scalars(select(Game.room_code).where(Game.status == LIVE)))


def test_a_lobby_and_a_running_game_come_back_after_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'game.db'}"
    with make_client(url) as before:
        lobby = make_room(before, 1)
        running = make_room(before, 1)
        start(before, running)
        post(before, f"/rooms/{running}/force")  # the game has moved on: a night has passed
        seen = state_of(before, running)
        assert codes_saved(before) == {lobby, running}
    with make_client(url) as after:  # a new process, the same database
        assert after.app.state.ww_store.codes() == {lobby, running}
        again = state_of(after, running)
        assert again["game"]["night"] == seen["game"]["night"] and again["game"]["phase"] == seen["game"]["phase"]
        assert [p["name"] for p in again["game"]["players"]] == [p["name"] for p in seen["game"]["players"]]
        assert post(after, f"/rooms/{running}/force").status_code == 200  # and it can be played on


def test_the_turn_timer_starts_again_and_a_restored_room_is_not_reaped_at_once(tmp_path):
    url = f"sqlite:///{tmp_path / 'game.db'}"
    with make_client(url) as before:
        code = make_room(before, 1, timerSeconds=30)
        start(before, code)
    with make_client(url) as after:
        room = after.app.state.ww_store.require(code)
        assert room.game.seconds_left() == pytest.approx(room.game.timer_budget(), abs=2)  # the whole turn again
        assert after.app.state.ww_store.reap() == []


def test_a_deleted_room_is_forgotten_and_does_not_come_back(tmp_path):
    url = f"sqlite:///{tmp_path / 'game.db'}"
    with make_client(url) as before:
        keep, gone = make_room(before, 1), make_room(before, 1)
        assert post(before, f"/rooms/{gone}/leave").status_code in (200, 204)  # the only human leaves: the room is deleted
        post(before, f"/rooms/{keep}/bots", json={"count": 1})  # the next change clears the copy of the deleted room
        assert codes_saved(before) == {keep}
    with make_client(url) as after:
        assert after.app.state.ww_store.codes() == {keep}


def test_a_room_has_one_live_row_and_a_finished_row_for_each_game_and_only_the_live_one_goes_with_the_room(tmp_path):
    url = f"sqlite:///{tmp_path / 'game.db'}"
    with make_client(url) as client:
        code = make_room(client, 2)
        start(client, code)
        play_out(client, code)
        post(client, f"/rooms/{code}/rematch")
        play_out(client, code)

        def kinds():
            with client.app.state.session_factory() as db:
                return sorted(db.execute(select(Game.status, Game.room_code).where(Game.room_code == code)).all())

        assert kinds() == [("finished", code), ("finished", code), ("live", code)]  # two games, one room
        client.app.state.ww_store.delete(code)
        post(client, f"/rooms/{make_room(client, 1)}/bots", json={"count": 1})  # the next change forgets the copy of the room
        assert kinds() == [("finished", code), ("finished", code)]  # what the game gave stays


def test_a_damaged_row_is_dropped_and_the_others_still_come_back(tmp_path):
    url = f"sqlite:///{tmp_path / 'game.db'}"
    with make_client(url) as before:
        good = make_room(before, 1)
        with before.app.state.session_factory() as db:
            db.add(Game(room_code="BADROW", status=LIVE, state=b"not a pickle"))
            db.commit()
    with make_client(url) as after:
        assert after.app.state.ww_store.codes() == {good}
        assert "BADROW" not in codes_saved(after)


def test_bytes_that_would_run_something_are_refused():
    class Evil:
        def __reduce__(self):
            import os

            return (os.system, ("echo pwned",))

    with pytest.raises(pickle.UnpicklingError):
        snapshots.load(pickle.dumps(Evil()), lambda: 0.0)
    with pytest.raises(pickle.UnpicklingError):
        snapshots.load(pickle.dumps({"a": 1}), lambda: 0.0)  # not a room


def test_dumping_leaves_the_live_room_untouched():
    store = RoomStore(clock=lambda: 5.0)
    room = store.create(1, "alice", count=6)
    room.start(1)
    clock, game_clock = room.clock, room.game._clock
    data = snapshots.dump(room)
    assert room.clock is clock and room.game._clock is game_clock and isinstance(data, bytes)
    restored = snapshots.load(data, lambda: 99.0)
    assert restored.code == room.code and restored.game._clock() == 99.0 and restored.last_active == 99.0
    assert not isinstance(io.BytesIO(data), type(None))


def test_a_saved_room_is_sealed_when_there_is_a_key_and_read_back_only_with_it(monkeypatch):
    from cryptography.fernet import Fernet

    store = RoomStore(clock=lambda: 5.0)
    room = store.create(1, "alice", count=6)
    room.start(1)
    plain = snapshots.dump(room)
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("WEREWOLF_SNAPSHOT_KEY", key)
    sealed = snapshots.dump(room)
    assert sealed.startswith(snapshots.SEALED) and b"alice" not in sealed  # nothing of the game can be read in the row
    assert snapshots.load(sealed, lambda: 9.0).code == room.code
    assert snapshots.load(plain, lambda: 9.0).code == room.code  # rows written before the key still come back
    monkeypatch.setenv("WEREWOLF_SNAPSHOT_KEY", Fernet.generate_key().decode())
    with pytest.raises(Exception):  # another key
        snapshots.load(sealed, lambda: 9.0)
    monkeypatch.delenv("WEREWOLF_SNAPSHOT_KEY")
    with pytest.raises(pickle.UnpicklingError):  # sealed, and no key
        snapshots.load(sealed, lambda: 9.0)
