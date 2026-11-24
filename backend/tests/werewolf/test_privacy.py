"""A living human must never learn another seat's role, ability, private night log or wolf chat.

The rule: a living player sees exactly their own perspective; the full log and other players' perspectives are for
the dead, and for everybody once the game is over. The host has no extra view.
"""
import json
import re
from contextlib import ExitStack

import pytest

from tests.werewolf.test_api import get, make_room, name_of, post, start
from tests.werewolf.test_ws import open_state

HUMANS = (1, 2, 3)
ROLES = (
    [{"faction": "VILLAGER", "ability": "SEE_FACTION"}, {"faction": "WOLF", "ability": "KILL"},
     {"faction": "VILLAGER", "ability": "BLOCK_EFFECTS"}, {"faction": "WOLF", "ability": "KILL_ON_DEATH"},
     {"faction": "VILLAGER", "ability": "REVEAL_ON_DEATH"}, {"faction": "VILLAGER", "ability": "KILL"}]
    + [{"faction": "VILLAGER", "ability": "NONE"}] * 4
    + [{"faction": "WOLF", "ability": "KILL_ON_DEATH"}, {"faction": "WOLF", "ability": "KILL_ON_DEATH"}]
)
FULL_LOG_LINE = re.compile(r"\((Người|Sói|Ma), ")  # only the omniscient log names an actor's faction
WOLF_ONLY_LINE = re.compile(r"kết quả riêng của Sói|Sói vote|vote Sói")


def room_of(client, code):
    return client.app.state.ww_store.get(code)


def state_of(client, code, uid):
    return get(client, f"/rooms/{code}", uid, name_of(uid)).json()["state"]


def assert_only_own_perspective(client, code):
    """Every living human's state equals their own engine perspective; dead/finished ones may know more."""
    room = room_of(client, code)
    game = room.game
    for uid in HUMANS:
        pid = room.player_id(uid)
        state = state_of(client, code, uid)["game"]
        perspective = get(client, f"/rooms/{code}/perspective/{pid}", uid, name_of(uid))
        me = game.players[pid - 1]
        if game.game_over or not me.alive:
            assert perspective.status_code == 200
            continue
        assert perspective.status_code == 403, "a living player must not be able to open perspectives"
        own = game.view_for(pid, perspective=True)
        assert state["players"] == own["players"]
        assert state["log"] == own["log"]
        assert state["chat"] == own["chat"]
        assert not any(FULL_LOG_LINE.search(line["text"]) for line in state["log"])
        if me.faction.name != "WOLF":
            assert not any(WOLF_ONLY_LINE.search(line["text"]) for line in state["log"])
            assert not any(m["channel"] == "wolf" for m in state["chat"])
        for other in state["players"]:
            if other["id"] != pid and other["ability"] is not None:
                assert game.public_info.get(other["id"], {}).get("ability") or \
                    game.wolf_info.get(other["id"], {}).get("ability"), "an ability leaked without being revealed"


def drive(client, code, per_step):
    """Humans take their first option each turn (the host forces the rest) until the game ends."""
    for _ in range(300):
        room = room_of(client, code)
        per_step()
        if room.game.game_over:
            return
        moved = False
        for uid in HUMANS:
            game = state_of(client, code, uid)["game"]
            todo = [a for a in game["actions"] if not a["submitted"]]
            if todo:
                act = todo[0]
                r = post(client, f"/rooms/{code}/action", uid, name_of(uid),
                         json={"target": act["options"][0] if act["options"] else 0,
                               "kind": "wolf" if act["kind"] == "wolf" else "ability"})
                assert r.status_code == 200
                moved = True
        if not moved:
            post(client, f"/rooms/{code}/force")
    raise AssertionError("game did not finish")


@pytest.fixture
def room_code(client):
    code = make_room(client, 3, seats=ROLES)
    start(client, code)
    return code


def test_living_players_only_ever_see_their_own_perspective_through_a_whole_game(client, room_code):
    drive(client, room_code, lambda: assert_only_own_perspective(client, room_code))


def test_the_host_has_no_extra_view(client, room_code):
    room = room_of(client, room_code)
    host = state_of(client, room_code, 1)["game"]
    own = room.game.view_for(room.player_id(1), perspective=True)
    assert host["players"] == own["players"] and host["log"] == own["log"]
    assert get(client, f"/rooms/{room_code}/perspective/2").status_code == 403


def test_lobby_state_never_shows_other_seats_roles(client):
    code = make_room(client, 2, seats=ROLES)
    for uid in (1, 2):
        members = state_of(client, code, uid)["members"]
        assert sum(1 for m in members if m["faction"] or m["ability"]) <= 1
        assert all(not (m["faction"] or m["ability"]) for m in members if not m["isYou"])


def test_dead_players_get_the_full_log_and_other_perspectives(client, room_code):
    room = room_of(client, room_code)
    victim = 2
    pid = room.player_id(victim)
    room.game.players[pid - 1].alive = False
    state = state_of(client, room_code, victim)["game"]
    assert state["log"]
    other = 1 if pid != 1 else 3
    view = get(client, f"/rooms/{room_code}/perspective/{room.player_id(other)}", victim, name_of(victim))
    assert view.status_code == 200 and view.json()["me"]["id"] == room.player_id(other)


def test_everything_is_revealed_when_the_game_is_over(client, room_code):
    drive(client, room_code, lambda: None)
    for uid in HUMANS:
        game = state_of(client, room_code, uid)["game"]
        assert game["gameOver"] and all(p["faction"] and p["ability"] for p in game["players"])
        assert get(client, f"/rooms/{room_code}/perspective/1", uid, name_of(uid)).status_code == 200


def test_rematch_does_not_leak_the_new_deal(client, room_code):
    drive(client, room_code, lambda: None)
    response = post(client, f"/rooms/{room_code}/rematch")
    assert response.status_code == 200
    host_state = response.json()["state"]
    for uid in HUMANS:
        state = state_of(client, room_code, uid)
        game = state["game"]
        assert not any(m["faction"] or m["ability"] for m in state["members"])  # no roles outside the game view
        me = next(p for p in game["players"] if p["id"] == game["me"]["id"])
        for other in game["players"]:
            if other["id"] != me["id"] and not game["gameOver"]:
                assert other["ability"] is None or game["me"]["alive"] is False
    assert host_state["game"]["me"]["id"] == 1
    assert_only_own_perspective(client, room_code)


def test_nothing_secret_is_ever_pushed_over_websockets(client, room_code, monkeypatch):
    hub = client.app.state.ww_hub
    seen: list[tuple[int, dict]] = []
    original = hub._deliver

    async def spy(room, socket, frame):
        seen.append((hub._rooms[room][socket], json.loads(frame)))
        return await original(room, socket, frame)

    monkeypatch.setattr(hub, "_deliver", spy)
    with ExitStack() as stack:
        for uid in HUMANS:
            open_state(client, stack, room_code, uid)
        seen.clear()
        drive(client, room_code, lambda: None)
        for uid in HUMANS:  # chat while it is possible (wolves at night, everybody by day)
            post(client, f"/rooms/{room_code}/chat", uid, name_of(uid), json={"text": "psst"})
    room = room_of(client, room_code)
    assert seen
    for uid, frame in seen:
        text = json.dumps(frame, ensure_ascii=False)
        if frame["type"] == "chat" and frame["message"]["channel"] == "wolf":
            assert uid in _wolf_users(room), "wolf chat reached a non-wolf"
        if frame["type"] == "state" and not frame["state"]["game"]["gameOver"] and frame["state"]["game"]["me"]["alive"]:
            assert not FULL_LOG_LINE.search(text), "the omniscient log reached a living player"


def _wolf_users(room):
    """Users whose seat is (or was dealt) a wolf at the start of the game."""
    return {seat.started_by for seat, p in zip(room.seats, room.game.players)
            if seat.started_by and p.ability.name in ("KILL", "KILL_ON_DEATH") and p.faction.name == "WOLF"} | \
        {seat.started_by for seat, p in zip(room.seats, room.game.players) if seat.started_by and p.faction.name == "GHOST"}
