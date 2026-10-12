import random
from dataclasses import replace

import pytest

from app.engine import (
    CHAT_ALL,
    CHAT_WOLVES,
    ForbiddenAction,
    Game,
    GameError,
    Phase,
    Player,
    Role,
    Winner,
    add_player,
    cast_vote,
    chat_recipients,
    chat_scope,
    end_discussion,
    force_advance,
    leave,
    new_game,
    resolve_night,
    role_deck,
    start_game,
    submit_action,
    view_for,
)

# ids: 1 host/villager, 2 villager, 3 villager, 4 wolf, 5 seer, 6 doctor, 7 wolf
ROLES = {
    1: Role.VILLAGER, 2: Role.VILLAGER, 3: Role.VILLAGER, 4: Role.WEREWOLF,
    5: Role.SEER, 6: Role.DOCTOR, 7: Role.WEREWOLF,
}


def running(roles: dict[int, Role] | None = None, phase: Phase = Phase.NIGHT) -> Game:
    chosen = roles or ROLES
    players = tuple(Player(uid, f"u{uid}", role) for uid, role in chosen.items())
    return Game(players=players, host_id=1, phase=phase, day=1)


def lobby(count: int) -> Game:
    game = new_game(1, "u1")
    for uid in range(2, count + 1):
        game = add_player(game, uid, f"u{uid}")
    return game


def night_all(game: Game, wolf_target: int, seer: int | None = None, doc: int | None = None) -> Game:
    for wolf in game.living(Role.WEREWOLF):
        game = submit_action(game, wolf.user_id, wolf_target)
    if seer is not None:
        game = submit_action(game, 5, seer)
    if doc is not None:
        game = submit_action(game, 6, doc)
    return game


def alive_ids(game: Game) -> set[int]:
    return {p.user_id for p in game.living()}


# ---- lobby ----

def test_new_game_has_host_in_lobby():
    game = new_game(1, "u1")
    assert game.phase is Phase.LOBBY and game.host_id == 1 and len(game.players) == 1


def test_add_player_rejects_duplicate_full_and_started():
    game = lobby(2)
    with pytest.raises(GameError):
        add_player(game, 2, "u2")
    with pytest.raises(GameError):
        add_player(lobby(12), 99, "x")
    with pytest.raises(GameError):
        add_player(running(), 99, "x")


def test_add_player_does_not_mutate_original():
    game = lobby(2)
    add_player(game, 3, "u3")
    assert len(game.players) == 2


@pytest.mark.parametrize("count,wolves", [(5, 1), (7, 1), (8, 2), (11, 2), (12, 3)])
def test_role_deck_composition(count, wolves):
    deck = role_deck(count)
    assert len(deck) == count
    assert deck.count(Role.WEREWOLF) == wolves
    assert deck.count(Role.SEER) == deck.count(Role.DOCTOR) == 1


def test_start_requires_host_and_minimum_players():
    with pytest.raises(ForbiddenAction):
        start_game(lobby(5), 2, random.Random(1))
    with pytest.raises(GameError):
        start_game(lobby(4), 1, random.Random(1))


def test_start_assigns_roles_deterministically_with_seed():
    first = start_game(lobby(8), 1, random.Random(42))
    second = start_game(lobby(8), 1, random.Random(42))
    assert first.phase is Phase.NIGHT and first.day == 1
    assert [p.role for p in first.players] == [p.role for p in second.players]
    assert all(p.role is not None for p in first.players)


def test_cannot_start_twice():
    started = start_game(lobby(5), 1, random.Random(1))
    with pytest.raises(GameError):
        start_game(started, 1, random.Random(1))


# ---- night actions ----

def test_actions_rejected_outside_night_and_for_non_members():
    with pytest.raises(GameError):
        submit_action(running(phase=Phase.DAY), 4, 1)
    with pytest.raises(ForbiddenAction):
        submit_action(running(), 99, 1)


def test_dead_players_cannot_act_or_be_targeted():
    game = running()
    game = game.with_player(replace(game.find(4), alive=False))
    with pytest.raises(GameError):
        submit_action(game, 4, 1)
    with pytest.raises(GameError):
        submit_action(game, 7, 4)


def test_villager_has_no_night_action():
    with pytest.raises(GameError):
        submit_action(running(), 1, 2)


def test_unknown_target_rejected():
    with pytest.raises(GameError):
        submit_action(running(), 4, 99)


def test_wolf_cannot_target_wolf():
    with pytest.raises(GameError):
        submit_action(running(), 4, 7)


def test_seer_cannot_inspect_self_or_twice():
    game = running()
    with pytest.raises(GameError):
        submit_action(game, 5, 5)
    game = submit_action(game, 5, 1)
    with pytest.raises(GameError):
        submit_action(game, 5, 2)


def test_doctor_cannot_protect_twice_per_night_or_same_target_consecutively():
    game = submit_action(running(), 6, 1)
    with pytest.raises(GameError):
        submit_action(game, 6, 2)
    with pytest.raises(GameError):
        submit_action(replace(running(), last_doctor_target=3), 6, 3)
    submit_action(replace(running(), last_doctor_target=3), 6, 6)  # self is fine


def test_night_waits_for_everyone_then_resolves():
    game = submit_action(running(), 4, 1)
    game = submit_action(game, 7, 1)
    game = submit_action(game, 5, 2)
    assert game.phase is Phase.NIGHT
    game = submit_action(game, 6, 3)
    assert game.phase is Phase.DAY
    assert 1 not in alive_ids(game)


def test_wolf_kill_reveals_role_publicly():
    game = night_all(running(), 1, seer=2, doc=3)
    kill = [e for e in game.events if e.kind == "night_death"]
    assert kill[0].player_id == 1 and kill[0].role == "villager"


def test_doctor_protection_saves_victim():
    game = night_all(running(), 1, seer=2, doc=1)
    assert game.phase is Phase.DAY and alive_ids(game) == set(ROLES)
    assert game.events[-1].kind == "peaceful_night"
    assert game.last_doctor_target == 1


def test_wolf_vote_tie_means_no_kill():
    game = submit_action(running(), 4, 1)
    game = submit_action(game, 7, 2)
    game = force_advance(game, 1)
    assert alive_ids(game) == set(ROLES)


def test_wolf_plurality_kills_target():
    roles = {**ROLES, 8: Role.WEREWOLF, 9: Role.VILLAGER, 10: Role.VILLAGER, 11: Role.VILLAGER,
             12: Role.VILLAGER}
    game = running(roles)
    game = submit_action(game, 4, 1)
    game = submit_action(game, 7, 1)
    game = submit_action(game, 8, 2)
    game = force_advance(game, 1)
    assert 1 not in alive_ids(game) and 2 in alive_ids(game)


def test_wolf_can_change_vote_before_resolution():
    game = submit_action(running(), 4, 1)
    game = submit_action(game, 4, 2)
    assert dict(game.wolf_votes)[4] == 2 and len(game.wolf_votes) == 1


def test_seer_result_is_recorded_and_accurate():
    game = night_all(running(), 1, seer=4, doc=2)
    assert game.seer_results == ((4, True),)
    game = replace(game, phase=Phase.NIGHT)
    game = night_all(game, 2, seer=3, doc=5)
    assert (3, False) in game.seer_results


def test_force_advance_night_without_actions_is_peaceful():
    game = force_advance(running(), 1)
    assert game.phase is Phase.DAY and alive_ids(game) == set(ROLES)


def test_resolve_night_outside_night_rejected():
    with pytest.raises(GameError):
        resolve_night(running(phase=Phase.DAY))


# ---- day, vote ----

def test_only_host_ends_discussion_and_only_in_day():
    day = running(phase=Phase.DAY)
    with pytest.raises(ForbiddenAction):
        end_discussion(day, 2)
    with pytest.raises(GameError):
        end_discussion(running(), 1)
    assert end_discussion(day, 1).phase is Phase.VOTE


def test_vote_validation():
    vote = running(phase=Phase.VOTE)
    with pytest.raises(GameError):
        cast_vote(running(phase=Phase.DAY), 1, 2)
    with pytest.raises(GameError):
        cast_vote(vote, 1, 1)
    with pytest.raises(GameError):
        cast_vote(vote, 1, 99)
    with pytest.raises(ForbiddenAction):
        cast_vote(vote, 99, 1)
    dead = vote.with_player(replace(vote.find(2), alive=False))
    with pytest.raises(GameError):
        cast_vote(dead, 2, 1)
    with pytest.raises(GameError):
        cast_vote(dead, 1, 2)


def vote_all(game: Game, choices: dict[int, int | None]) -> Game:
    for voter, target in choices.items():
        game = cast_vote(game, voter, target)
    return game


def test_majority_lynches_and_reveals_role():
    game = vote_all(running(phase=Phase.VOTE), {1: 4, 2: 4, 3: 4, 4: 1, 5: 4, 6: 4, 7: 1})
    assert 4 not in alive_ids(game)
    assert game.phase is Phase.NIGHT and game.day == 2
    lynch = [e for e in game.events if e.kind == "lynch"][0]
    assert lynch.role == "werewolf"


def test_tie_lynches_nobody():
    game = vote_all(running(phase=Phase.VOTE), {1: 4, 2: 4, 3: 1, 4: 1, 5: None, 6: None, 7: None})
    assert alive_ids(game) == set(ROLES)
    assert game.events[-1].kind == "no_lynch" and game.phase is Phase.NIGHT


def test_all_abstain_lynches_nobody():
    game = vote_all(running(phase=Phase.VOTE), {uid: None for uid in ROLES})
    assert alive_ids(game) == set(ROLES)


def test_plurality_without_absolute_majority_still_lynches():
    game = vote_all(running(phase=Phase.VOTE), {1: 3, 2: 3, 3: 2, 4: None, 5: None, 6: None, 7: None})
    assert 3 not in alive_ids(game)


def test_vote_can_be_changed_before_phase_ends():
    game = cast_vote(running(phase=Phase.VOTE), 1, 2)
    game = cast_vote(game, 1, 3)
    assert dict(game.votes)[1] == 3 and len(game.votes) == 1


def test_force_advance_vote_single_vote_lynches_nobody():
    game = cast_vote(running(phase=Phase.VOTE), 1, 2)
    game = force_advance(game, 1)
    assert alive_ids(game) == set(ROLES) and game.events[-1].kind == "no_lynch"


def test_force_advance_vote_without_strict_majority_lynches_nobody():
    # 7 living players: 3 of 7 is a plurality but not a majority
    game = vote_all(running(phase=Phase.VOTE), {1: 3, 2: 3, 4: 3, 5: 2})
    assert alive_ids(force_advance(game, 1)) == set(ROLES)


def test_force_advance_vote_with_strict_majority_lynches():
    game = vote_all(running(phase=Phase.VOTE), {1: 3, 2: 3, 4: 3, 5: 3})
    assert 3 not in alive_ids(force_advance(game, 1))


def test_force_advance_night_requires_wolf_majority():
    roles = {**ROLES, 8: Role.WEREWOLF, 9: Role.VILLAGER, 10: Role.VILLAGER, 11: Role.VILLAGER,
             12: Role.VILLAGER}
    one_of_three = force_advance(submit_action(running(roles), 4, 1), 1)
    assert 1 in alive_ids(one_of_three)
    two_of_three = submit_action(submit_action(running(roles), 4, 1), 7, 1)
    assert 1 not in alive_ids(force_advance(two_of_three, 1))


def test_force_advance_night_ignores_actions_of_dead_role_holders():
    game = running()
    game = game.with_player(replace(game.find(6), alive=False))  # the doctor
    game = replace(game, doctor_target=1, wolf_votes=((4, 1), (7, 1)))
    resolved = force_advance(game, 1)
    assert 1 not in alive_ids(resolved) and resolved.last_doctor_target is None


def test_force_advance_night_ignores_wolf_votes_of_dead_wolves():
    game = running()
    game = game.with_player(replace(game.find(7), alive=False))
    game = replace(game, wolf_votes=((7, 1),))
    assert alive_ids(force_advance(game, 1)) == alive_ids(game)


def test_force_advance_rules():
    with pytest.raises(ForbiddenAction):
        force_advance(running(), 2)
    with pytest.raises(GameError):
        force_advance(running(phase=Phase.FINISHED), 1)
    assert force_advance(running(phase=Phase.DAY), 1).phase is Phase.VOTE


# ---- win conditions ----

def test_villagers_win_when_last_wolf_lynched():
    roles = {1: Role.VILLAGER, 2: Role.VILLAGER, 3: Role.WEREWOLF, 4: Role.SEER, 5: Role.DOCTOR}
    game = vote_all(running(roles, Phase.VOTE), {1: 3, 2: 3, 3: 1, 4: 3, 5: 3})
    assert game.phase is Phase.FINISHED and game.winner is Winner.VILLAGE


def test_wolves_win_when_night_kill_reaches_parity():
    roles = {1: Role.VILLAGER, 2: Role.VILLAGER, 3: Role.WEREWOLF}
    game = submit_action(running(roles), 3, 1)
    assert game.phase is Phase.FINISHED and game.winner is Winner.WOLVES


def test_wolves_win_on_parity_after_lynch():
    roles = {1: Role.VILLAGER, 2: Role.VILLAGER, 3: Role.VILLAGER, 4: Role.WEREWOLF, 5: Role.WEREWOLF}
    game = vote_all(running(roles, Phase.VOTE), {1: 2, 2: 1, 3: 2, 4: 2, 5: 2})
    assert game.winner is Winner.WOLVES


def test_game_continues_when_no_win_condition():
    game = night_all(running(), 1, seer=2, doc=3)
    assert game.winner is None and game.phase is Phase.DAY


def test_no_actions_after_finish():
    roles = {1: Role.VILLAGER, 2: Role.VILLAGER, 3: Role.WEREWOLF}
    game = submit_action(running(roles), 3, 1)
    with pytest.raises(GameError):
        submit_action(game, 3, 2)
    with pytest.raises(GameError):
        cast_vote(game, 2, 3)


# ---- leaving ----

def test_leave_lobby_removes_player_and_transfers_host():
    game = leave(lobby(3), 1)
    assert [p.user_id for p in game.players] == [2, 3] and game.host_id == 2
    with pytest.raises(GameError):
        leave(game, 1)


def test_leave_running_game_eliminates_and_keeps_record():
    game = leave(running(), 1)
    player = game.find(1)
    assert player is not None and player.left and not player.alive
    assert game.member(1) is None and game.host_id != 1
    assert game.events[-1].kind == "left"


def test_leaving_last_pending_actor_resolves_night():
    game = night_all(running(), 1, seer=2)
    assert game.phase is Phase.NIGHT
    game = leave(game, 6)
    assert game.phase is Phase.DAY


def test_leaving_can_end_game():
    roles = {1: Role.VILLAGER, 2: Role.VILLAGER, 3: Role.WEREWOLF}
    game = leave(running(roles), 1)
    assert game.winner is Winner.WOLVES


def test_leaving_during_vote_completes_it():
    game = running(phase=Phase.VOTE)
    game = vote_all(game, {1: 4, 2: 4, 3: 4, 4: 1, 5: 4, 6: 4})
    game = leave(game, 7)
    assert game.winner is Winner.VILLAGE and 4 not in alive_ids(game)


def test_dead_player_leaving_only_flags_left():
    game = running()
    game = game.with_player(replace(game.find(2), alive=False))
    after = leave(game, 2)
    assert after.find(2).left and after.events == game.events


def test_leave_removes_votes_cast_for_leaver():
    game = cast_vote(running(phase=Phase.VOTE), 1, 2)
    assert dict(leave(game, 2).votes) == {}


def test_leave_finished_removes_player():
    game = replace(running(), phase=Phase.FINISHED)
    assert leave(game, 3).find(3) is None


# ---- secrecy of views ----

def test_villager_view_never_contains_other_living_roles():
    game = running()
    view = view_for(game, 1)
    others = [p for p in view["players"] if p["id"] != 1]
    assert all(p["role"] is None for p in others)
    assert view["you"]["role"] == "villager"


def test_serialised_view_hides_secrets_from_villager():
    import json

    text = json.dumps(view_for(night_all(running(), 3, seer=4), 1))
    assert "werewolf" not in text.replace('"role": "villager"', "")
    assert "inspections" not in text and "blocked_target" not in text


def test_wolves_see_each_other_only():
    view = view_for(running(), 4)
    roles = {p["id"]: p["role"] for p in view["players"]}
    assert roles[7] == "werewolf" and roles[4] == "werewolf"
    assert roles[5] is None and roles[6] is None and roles[1] is None


def test_dead_roles_are_public_and_finished_reveals_all():
    game = running()
    game = game.with_player(replace(game.find(5), alive=False))
    assert {p["id"]: p["role"] for p in view_for(game, 1)["players"]}[5] == "seer"
    done = replace(game, phase=Phase.FINISHED)
    assert all(p["role"] for p in view_for(done, 1)["players"])


def test_seer_and_doctor_private_data_only_for_owner():
    game = replace(running(), seer_results=((4, True),), last_doctor_target=2)
    assert view_for(game, 5)["you"]["inspections"] == [{"id": 4, "is_werewolf": True}]
    assert view_for(game, 6)["you"]["blocked_target"] == 2
    assert "inspections" not in view_for(game, 6)["you"]
    assert "blocked_target" not in view_for(game, 5)["you"]


def test_non_member_sees_names_but_no_roles():
    view = view_for(running(), 99)
    assert view["you"] is None and all(p["role"] is None for p in view["players"])


def test_pending_action_and_target_hints():
    game = submit_action(running(), 5, 1)
    assert view_for(game, 5)["you"]["pending"] is None
    assert view_for(game, 5)["you"]["target"] == 1
    assert view_for(game, 4)["you"]["pending"] == "kill"
    assert view_for(game, 6)["you"]["pending"] == "protect"
    assert view_for(game, 1)["you"]["pending"] is None
    vote = cast_vote(running(phase=Phase.VOTE), 1, 2)
    assert view_for(vote, 1)["you"]["pending"] is None
    assert view_for(vote, 2)["you"]["pending"] == "vote"
    assert view_for(running(phase=Phase.DAY), 2)["you"]["pending"] is None


# ---- chat permissions ----

def test_chat_scopes_by_phase():
    night, day = running(), running(phase=Phase.DAY)
    assert chat_scope(night, 4) == CHAT_WOLVES
    assert chat_scope(night, 1) is None
    assert chat_scope(day, 1) == CHAT_ALL
    assert chat_scope(lobby(2), 2) == CHAT_ALL
    assert chat_scope(day, 99) is None


def test_dead_players_cannot_chat_and_wolf_chat_stays_private():
    day = running(phase=Phase.DAY)
    dead = day.with_player(replace(day.find(1), alive=False))
    assert chat_scope(dead, 1) is None
    assert chat_recipients(day, CHAT_WOLVES) == {4, 7}
    assert chat_recipients(day, CHAT_ALL) == set(ROLES)
    done = replace(dead, phase=Phase.FINISHED)
    assert chat_scope(done, 1) == CHAT_ALL
