"""The host sets the role of each seat before the game starts: dealt at random, or one by one; only the host sees the setup."""

from tests.werewolf.conftest import auth_cookie
from tests.werewolf.test_api import get, make_room, post, seats, start


def roles_of(state):
    return [None if s is None else (s["faction"]["code"], s["ability"]["code"]) for s in state["setup"]]


def test_the_host_deals_the_roles_at_random_and_sees_them_for_every_seat(client):
    code = make_room(client, humans=1)
    response = post(client, f"/rooms/{code}/roles", json={"random": True})
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert len(state["setup"]) == len(state["members"]) and all(state["setup"])
    factions = {s["faction"]["code"] for s in state["setup"]}
    assert {"WOLF", "VILLAGER"} <= factions


def test_a_new_deal_changes_the_roles_often_enough_to_be_random(client):
    code = make_room(client, humans=1, count=12)
    seen = {tuple(roles_of(post(client, f"/rooms/{code}/roles", json={"random": True}).json()["state"])) for _ in range(6)}
    assert len(seen) > 1


def test_the_host_sets_the_roles_one_by_one_and_the_game_uses_them(client):
    code = make_room(client, humans=1)
    chosen = seats(5, {2: {"faction": "WOLF", "ability": "KILL"}})
    response = post(client, f"/rooms/{code}/roles", json={"seats": chosen})
    assert response.status_code == 200, response.text
    assert roles_of(response.json()["state"])[2] == ("WOLF", "KILL")
    state = start(client, code)
    assert state["started"] is True


def test_only_the_host_sets_roles_and_only_before_the_start(client):
    code = make_room(client, humans=2)
    assert post(client, f"/rooms/{code}/roles", 2, "user2", json={"random": True}).status_code == 403
    assert "setup" not in get(client, f"/rooms/{code}", 2, "user2").json()["state"]  # the others see no setup
    start(client, code)
    assert post(client, f"/rooms/{code}/roles", json={"random": True}).status_code in (400, 409)


def test_a_bad_set_of_roles_is_refused_and_nothing_changes(client):
    code = make_room(client, humans=1)
    before = post(client, f"/rooms/{code}/roles", json={"random": True}).json()["state"]["setup"]
    all_villagers = [{"faction": "VILLAGER", "ability": "NONE"}] * 5
    assert post(client, f"/rooms/{code}/roles", json={"seats": all_villagers}).status_code in (400, 409, 422)
    wrong_count = [{"faction": "WOLF", "ability": "KILL"}, {"faction": "VILLAGER", "ability": "NONE"}]
    assert post(client, f"/rooms/{code}/roles", json={"seats": wrong_count}).status_code in (400, 409, 422)
    state = post(client, f"/rooms/{code}/roles", json={}).json()["state"]
    assert state["setup"] == [None] * len(before)  # neither: the setup is cleared, to be dealt at the start


# ---- abilities the random deal leaves out ----


def abilities_of(state):
    return {s["ability"]["code"] for s in state["setup"] if s}


def test_a_random_deal_leaves_out_the_abilities_it_is_told_to(client):
    code = make_room(client, humans=1, count=30)
    banned = ["BLOCK_EFFECTS", "REVERSE_ABILITY", "SEE_FACTION", "KILL_ON_DEATH"]
    for _ in range(5):
        response = post(client, f"/rooms/{code}/roles", json={"random": True, "banned": banned})
        assert response.status_code == 200, response.text
        used = abilities_of(response.json()["state"])
        assert not used & set(banned)
        assert "KILL" in used  # the wolves that kill are still there


def test_a_deal_without_some_abilities_never_holds_them(client):
    from api.werewolf.engine.roles import Ability, suggest_roles

    for _ in range(20):
        roles = suggest_roles(30, [Ability.REVEAL_ON_DEATH, Ability.SEE_ABILITY])
        assert not {ability for _faction, ability in roles} & {Ability.REVEAL_ON_DEATH, Ability.SEE_ABILITY}


def test_what_the_game_needs_cannot_be_banned_and_a_group_cannot_be_emptied(client):
    code = make_room(client, humans=1)
    for name in ("KILL", "TRANSFORM", "NONE"):
        assert post(client, f"/rooms/{code}/roles", json={"random": True, "banned": [name]}).status_code == 400, name
    both = post(client, f"/rooms/{code}/roles", json={"random": True, "banned": ["BLOCK_EFFECTS", "REVERSE_EFFECTS"]})
    assert both.status_code == 400  # no defensive ability would be left
    assert post(client, f"/rooms/{code}/roles", json={"random": True, "banned": ["NOT_AN_ABILITY"]}).status_code == 422


def test_the_setup_says_what_can_be_banned(client):
    meta = client.get("/setup/meta", headers=auth_cookie()).json()
    assert "KILL_ON_DEATH" in meta["bannable"] and not {"KILL", "TRANSFORM", "NONE"} & set(meta["bannable"])


def test_banning_the_death_kill_makes_every_wolf_kill_openly(client):
    from api.werewolf.engine.roles import Ability, Faction, suggest_roles

    roles = suggest_roles(30, [Ability.KILL_ON_DEATH])
    assert {ability for faction, ability in roles if faction is Faction.WOLF} == {Ability.KILL}
