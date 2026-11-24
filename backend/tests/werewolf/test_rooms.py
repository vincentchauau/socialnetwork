"""Room domain: seats, lobby flow, results, rematch/reset, leaving, and what a state reveals."""
import random

import pytest

from api.werewolf.engine import Ability, Faction, GameError, Phase
from api.werewolf.rooms import Forbidden, Room, RoomError, RoomNotFound, Seat
from api.werewolf.store import RoomStore

F, A = Faction, Ability
ROLES5 = [(F.VILLAGER, A.SEE_FACTION), (F.WOLF, A.KILL), (F.VILLAGER, A.NONE), (F.VILLAGER, A.NONE),
          (F.VILLAGER, A.BLOCK_EFFECTS)]


def lobby(n=5, roles=None, host=1, name="host", **kw) -> Room:
    return RoomStore(rng=random.Random(1)).create(host, name, roles=roles, count=None if roles else n, **kw)


def finish(room: Room) -> None:
    for _ in range(200):
        if room.game.game_over:
            return
        room.game.force()
    raise AssertionError("game did not finish")


def test_create_gives_host_seat_one_and_bots_elsewhere():
    room = lobby(6)
    assert room.seats[0].user_id == 1 and room.seats[0].name == "host"
    assert all(s.is_bot for s in room.seats[1:]) and len(room.seats) == 6
    assert len({s.name.casefold() for s in room.seats}) == 6  # unique names


def test_join_replaces_a_bot_in_place_and_keeps_its_role():
    room = lobby(roles=ROLES5)
    room.join(2, "bob", random.Random(4))
    taken = next(s for s in room.seats if s.user_id == 2)
    index = room.seats.index(taken)
    assert (taken.faction, taken.ability) == ROLES5[index] and index != 0
    assert len(room.seats) == 5 and sum(s.is_bot for s in room.seats) == 3


def test_join_prefers_the_bot_with_the_same_name_case_insensitively():
    room = lobby()
    bot_name = room.seats[3].name
    room.join(2, bot_name.upper())
    assert room.seats[3].user_id == 2 and room.seats[3].name == bot_name.upper()
    assert [s.name.casefold() for s in room.seats].count(bot_name.casefold()) == 1


def test_join_rejects_duplicates_full_rooms_and_started_games():
    room = lobby()
    with pytest.raises(RoomError, match="đã ở trong"):
        room.join(1, "host")
    for uid in range(2, 6):
        room.join(uid, f"u{uid}")
    with pytest.raises(RoomError, match="đầy"):
        room.join(9, "late")
    room.start(1)
    with pytest.raises(RoomError, match="đã bắt đầu"):
        room.join(9, "late")


def test_join_rejects_a_name_used_by_a_human():
    room = lobby()
    room.seats[1].user_id, room.seats[1].name = 7, "Zed"  # a human called Zed
    with pytest.raises(RoomError, match="Tên"):
        room.join(8, "zed")


def test_add_bots_is_host_only_lobby_only_and_bounded():
    room = lobby()
    with pytest.raises(Forbidden):
        room.add_bots(2, 1)
    room.add_bots(1, 35)
    assert len(room.seats) == 40
    with pytest.raises(RoomError, match="đầy"):
        room.add_bots(1, 1)
    room.start(1)
    with pytest.raises(RoomError):
        room.add_bots(1, 1)


def test_start_rules():
    room = lobby()
    with pytest.raises(Forbidden):
        room.start(2)
    room.seats = room.seats[:3]
    with pytest.raises(RoomError, match="ít nhất 5"):
        room.start(1)
    room = lobby()
    room.start(1)
    with pytest.raises(RoomError, match="đã bắt đầu"):
        room.start(1)


def test_start_needs_a_human():
    room = lobby()
    room.seats[0].user_id = None
    with pytest.raises(RoomError, match="người chơi thật"):
        room.start(1)


def test_dealt_roles_are_dealt_again_when_the_number_of_people_changes():
    room = lobby(5)
    room.set_roles(1, None, randomise=True)
    assert all(s.faction for s in room.seats) and len(room.seats) == 5
    names = [("a", "virtual"), ("b", "virtual"), ("c", "virtual"), ("d", "virtual"), ("e", "virtual"), ("f", "virtual"), ("g", "virtual")]
    assert room.follow_chat(names, 12)
    assert len(room.seats) == 12 and all(s.faction and s.ability for s in room.seats)  # every new seat has a role: dealt for 12, not 5
    assert sum(s.faction == F.GHOST for s in room.seats) == 1  # 12 people: the ghosts of the bigger game
    assert room.follow_chat(names[:3], 6)
    assert len(room.seats) == 6 and all(s.faction for s in room.seats) and sum(s.faction == F.GHOST for s in room.seats) == 0


def test_roles_that_were_never_dealt_stay_undealt_when_people_come():
    room = lobby(5)
    assert room.follow_chat([("a", "virtual")] * 1 + [("b", "virtual")], 8)
    assert len(room.seats) == 8 and not any(s.faction for s in room.seats)  # still dealt at the start


def test_preset_roles_are_used_when_every_seat_has_one():
    room = lobby(roles=ROLES5)
    room.start(1)
    assert [(p.faction, p.ability) for p in room.game.players] == ROLES5


def test_incomplete_setup_is_dealt_at_random():
    room = lobby(roles=ROLES5)
    room.add_bots(1, 2)  # new seats have no role: everything is re-dealt
    room.start(1)
    assert len(room.game.players) == 7 and sum(p.faction == F.WOLF for p in room.game.players) == 2


def test_game_options_are_forwarded():
    room = lobby(timer=30, events=False, dead_talk=False)
    room.start(1)
    g = room.game
    assert g.timer == 30 and g.events_enabled is False and g.dead_talk is False


def test_state_hides_every_other_seats_role_in_the_lobby():
    room = lobby(roles=ROLES5)
    room.join(2, "bob", random.Random(2))
    for uid in (1, 2):
        state = room.state_for(uid)
        shown = [m for m in state["members"] if m["faction"] or m["ability"]]
        assert [m["isYou"] for m in shown] == [True]  # only the caller's own seat shows a role
    outsider = room.state_for(99)
    assert all(m["faction"] is None and m["ability"] is None for m in outsider["members"])
    assert outsider["you"] is None and outsider["game"] is None and not outsider["isHost"]


def test_state_shape_and_host_flag():
    room = lobby()
    room.join(2, "bob")
    s1, s2 = room.state_for(1), room.state_for(2)
    assert s1["isHost"] and not s2["isHost"]
    assert s2["you"] == {"username": "bob", "seat": room.seat_index(2) + 1}
    assert s1["code"] == room.code and s1["minPlayers"] == 5 and s1["maxPlayers"] == 40
    assert [m["isHost"] for m in s1["members"]].count(True) == 1


def test_results_are_collected_once_with_humans_only():
    room = lobby(roles=ROLES5)
    room.join(2, "bob")
    room.start(1)
    finish(room)
    record = room.collect_result()
    assert record is not None and room.collect_result() is None
    assert {p.user_id for p in record.players} == {1, 2} and record.size == 5
    assert room.history["games"] == 1
    assert all(p.outcome in ("won", "lost", "draw") for p in record.players)
    assert all(p.user_id > 0 for p in record.players)  # a bot is never a user


def test_result_outcome_follows_the_final_faction():
    room = lobby(roles=ROLES5)
    room.start(1)
    finish(room)
    record = room.collect_result()
    winner = room.game.winner
    mine = record.players[0]
    expected = "draw" if winner is None else ("won" if room.game.players[0].faction == winner else "lost")
    assert mine.outcome == expected and record.winner == (winner.name if winner else "DRAW")


def test_rematch_needs_host_and_a_finished_game_and_redeals():
    room = lobby(roles=ROLES5)
    room.start(1)
    with pytest.raises(RoomError):
        room.rematch(1)
    finish(room)
    with pytest.raises(Forbidden):
        room.rematch(2)
    old = room.game
    room.rematch(1)
    assert room.game is not old and room.game.night >= 1  # a fresh game (bots may even finish it at once)
    assert room.history["games"] == 1 and len(room.records) == 1
    assert all(s.faction is None for s in room.seats)


def test_reset_drops_bots_keeps_humans_and_refills():
    room = lobby(6)
    room.join(2, "bob")
    room.start(1)
    room.reset(1)
    assert room.game is None and len(room.seats) == 5
    assert {s.user_id for s in room.seats if s.user_id} == {1, 2}
    with pytest.raises(Forbidden):
        room.reset(2)


def test_force_is_host_only_and_needs_a_game():
    room = lobby()
    with pytest.raises(Forbidden):
        room.force(2)
    with pytest.raises(RoomError):
        room.force(1)
    room.start(1)
    room.force(1)


def test_leave_in_lobby_turns_the_seat_into_a_bot_and_moves_host():
    room = lobby(roles=ROLES5)
    room.join(2, "bob")
    seat_no = room.seat_index(2)
    assert room.leave(1) is False
    assert room.host_id == 2 and room.seats[0].is_bot
    assert room.seats[0].faction == ROLES5[0][0]  # the seat keeps its role
    assert room.seat_index(2) == seat_no
    assert room.leave(2) is True  # nobody left


def test_leave_unknown_user():
    with pytest.raises(RoomError):
        lobby().leave(5)


def test_leaving_a_running_game_hands_the_seat_to_a_bot():
    room = lobby()
    room.join(2, "bob")
    room.start(1)
    index = room.seat_index(2)
    assert room.leave(2) is False
    assert room.seats[index].user_id is None and room.game.players[index].is_bot
    assert room.seats[index].started_by == 2  # the result still credits who started
    assert room.state_for(2)["you"] is None


def test_leaving_never_blocks_the_game():
    room = lobby()
    room.join(2, "bob")
    room.start(1)
    room.leave(2)
    finish(room)
    record = room.collect_result()
    assert {p.user_id for p in record.players} == {1, 2}


def test_leaving_after_game_over_just_frees_the_seat():
    room = lobby()
    room.start(1)
    finish(room)
    assert room.leave(1) is True and room.seats[0].is_bot


def test_in_game_actions_require_a_seat_and_a_game():
    room = lobby()
    with pytest.raises(RoomError):
        room.submit(1, 0)
    with pytest.raises(RoomError):
        room.chat(1, "hi")
    room.start(1)
    with pytest.raises(Forbidden):
        room.submit(9, 0)
    with pytest.raises(Forbidden):
        room.chat(9, "hi")


def test_perspective_rules():
    room = lobby(roles=ROLES5)
    room.start(1)
    with pytest.raises(Forbidden, match="đã chết"):
        room.perspective(1, 2)
    with pytest.raises(Forbidden):
        room.perspective(9, 2)
    room.game.players[0].alive = False  # dead players may look
    assert room.perspective(1, 2)["me"]["id"] == 2
    with pytest.raises(RoomNotFound):
        room.perspective(1, 99)


def test_perspective_before_start_is_a_conflict():
    with pytest.raises(RoomError):
        lobby().perspective(1, 1)


def test_chat_recipients_follow_channel_visibility():
    room = lobby(roles=[(F.WOLF, A.KILL), (F.WOLF, A.KILL_ON_DEATH), (F.VILLAGER, A.NONE),
                        (F.VILLAGER, A.NONE), (F.VILLAGER, A.NONE)])
    room.join(2, "bob", random.Random(0))
    room.start(1)
    assert room.game.phase == Phase.NIGHT
    message = room.chat(1, "đêm nay giết ai?")
    bob_is_wolf = room.game.players[room.seat_index(2)].faction == F.WOLF
    assert room.chat_recipients(message) == ([1, 2] if bob_is_wolf else [1])
    assert room.chat_payload(message)["channel"] == "wolf"


def test_summary():
    room = lobby(roles=ROLES5, title="Làng Test", timer=30, events=False)
    assert room.summary() == {"id": room.code, "title": "Làng Test", "host": "host", "players": 1, "seats": 5,
                              "open_seats": 4, "max_players": 40, "timer": 30, "events": False}


def test_tick_forces_an_expired_turn_with_an_injected_clock():
    now = [100.0]
    room = RoomStore(clock=lambda: now[0], rng=random.Random(1)).create(1, "h", roles=ROLES5, timer=30)
    room.start(1)
    room.state_for(1)  # first observation starts the countdown
    assert not room.tick()
    now[0] += 31
    assert room.tick() and room.game.night >= 1


def test_seat_dataclass_is_bot_flag():
    assert Seat("x").is_bot and not Seat("x", 3).is_bot
    assert issubclass(RoomError, GameError)
