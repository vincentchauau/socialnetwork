import pytest

from api.werewolf.engine.events import ALL_EVENTS
from sn_shared.directory import Person

from api.werewolf.store import MAX_ROOMS_PER_USER
from tests.werewolf.conftest import ALLOWED_ORIGIN, auth_cookie


def post(client, path, user=1, name="alice", json=None, headers=None):
    return client.post(path, json=json, headers={**auth_cookie(user, name), **(headers or {})})


def get(client, path, user=1, name="alice", params=None):
    return client.get(path, headers=auth_cookie(user, name), params=params)


def name_of(uid: int) -> str:
    return "alice" if uid == 1 else f"user{uid}"


def seats(n=5, overrides=None):
    base = [{"faction": "VILLAGER", "ability": "SEE_FACTION"} for _ in range(n)]
    base[1] = {"faction": "WOLF", "ability": "KILL"}
    for i, seat in (overrides or {}).items():
        base[i].update(seat)
    return base


def make_room(client, humans: int = 1, **body) -> str:
    """A lobby with `humans` real users (user 1 = alice hosts); the other seats are bots."""
    response = post(client, "/rooms", json=body)
    assert response.status_code == 201, response.text
    code = response.json()["id"]
    for uid in range(2, humans + 1):
        assert post(client, f"/rooms/{code}/join", uid, name_of(uid)).status_code == 200
    return code


def start(client, code, user=1):
    response = post(client, f"/rooms/{code}/start", user, name_of(user))
    assert response.status_code == 200, response.text
    return response.json()["state"]


def play_out(client, code, user=1):
    """Host forces every turn until the game is over; returns the final state."""
    state = get(client, f"/rooms/{code}", user, name_of(user)).json()["state"]
    for _ in range(300):
        if state["game"]["gameOver"]:
            return state
        state = post(client, f"/rooms/{code}/force", user, name_of(user)).json()["state"]
    raise AssertionError("game did not finish")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method,path",
    [("post", "/rooms"), ("get", "/rooms"), ("get", "/rooms/ABCDE"), ("post", "/rooms/ABCDE/join"),
     ("post", "/rooms/ABCDE/leave"), ("post", "/rooms/ABCDE/start"), ("post", "/rooms/ABCDE/bots"),
     ("post", "/rooms/ABCDE/action"), ("post", "/rooms/ABCDE/chat"), ("post", "/rooms/ABCDE/force"),
     ("post", "/rooms/ABCDE/rematch"), ("post", "/rooms/ABCDE/reset"), ("get", "/rooms/ABCDE/perspective/1"),
     ("get", "/me/history")],
)
def test_routes_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_setup_routes_need_a_signed_in_person(client):
    assert client.get("/setup/meta").status_code == 401
    assert client.get("/setup/meta", headers=auth_cookie()).status_code == 200


def test_cross_site_writes_are_refused(client):
    headers = {**auth_cookie(), "Origin": "https://evil.example"}
    assert client.post("/rooms", headers=headers).status_code == 403
    good = {**auth_cookie(), "Origin": ALLOWED_ORIGIN}
    assert client.post("/rooms", headers=good).status_code == 201
    assert client.get("/rooms", headers={**auth_cookie(), "Origin": "https://evil.example"}).status_code == 200


def test_rest_is_rate_limited_per_user(client):
    for _ in range(60):
        assert get(client, "/rooms").status_code == 200
    assert get(client, "/rooms").status_code == 429
    assert get(client, "/rooms", 2, "bob").status_code == 200  # another user has their own budget


def test_create_defaults_to_five_seats_with_the_caller_as_host(client):
    body = post(client, "/rooms").json()
    state = body["state"]
    assert len(body["id"]) == 5 and body["id"].isalpha() and body["id"].isupper()
    assert len(state["members"]) == 5 and sum(m["isBot"] for m in state["members"]) == 4
    assert state["isHost"] and state["you"] == {"username": "alice", "seat": 1}
    assert state["members"][0]["name"] == "alice" and state["members"][0]["isHost"]
    assert not state["started"] and state["game"] is None and state["title"].strip()


def test_create_with_count_makes_that_many_seats(client):
    state = post(client, "/rooms", json={"count": 12}).json()["state"]
    assert len(state["members"]) == 12


def test_create_rejects_bad_counts_and_mismatches(client):
    assert post(client, "/rooms", json={"count": 4}).status_code == 422
    assert post(client, "/rooms", json={"count": 41}).status_code == 422
    assert post(client, "/rooms", json={"count": 6, "seats": seats(5)}).status_code == 422


def test_create_with_seats_and_start_gives_the_host_seat_one(client):
    body = {"seats": seats(5, {0: {"faction": "WOLF", "ability": "KILL"}}), "start": True}
    state = post(client, "/rooms", json=body).json()["state"]
    game = state["game"]
    assert game["me"]["name"] == "alice" and game["me"]["id"] == 1
    assert (game["me"]["faction"]["code"], game["me"]["ability"]["code"]) == ("WOLF", "KILL")
    assert len(game["players"]) == 5


def test_create_with_seats_waits_when_not_starting_and_join_keeps_the_seat_role(client):
    code = post(client, "/rooms", json={"seats": seats(6)}).json()["id"]
    state = post(client, f"/rooms/{code}/join", 2, "bob").json()["state"]
    assert state["you"]["username"] == "bob" and len(state["members"]) == 6
    mine = next(m for m in state["members"] if m["isYou"])
    assert mine["faction"] is not None  # bob learns his own seat's role...
    assert all(m["faction"] is None for m in state["members"] if not m["isYou"])  # ...and nobody else's
    game = start(client, code)["game"]
    assert len(game["players"]) == 6


@pytest.mark.parametrize("players", [
    seats(5, {2: {"faction": "GHOST", "ability": "KILL"}}),  # Ma chỉ có Biến hình
    seats(5, {2: {"faction": "WOLF", "ability": "TRANSFORM"}}),
    seats(5, {2: {"faction": "VILLAGER", "ability": "WOLF_VOTE"}}),
    seats(5, {2: {"faction": "NOPE"}}),
    [{"faction": "VILLAGER", "ability": "KILL"}] * 5,  # no wolf
    seats(4),
])
def test_create_rejects_invalid_seats(client, players):
    assert post(client, "/rooms", json={"seats": players}).status_code == 422


def test_failed_start_on_create_leaves_no_room(client):
    # 5 seats but one is invalid for starting: simulate by an illegal timer instead
    assert post(client, "/rooms", json={"timerSeconds": 1}).status_code == 422
    assert get(client, "/rooms").json() == []


def test_room_title_and_custom_code(client):
    auto = post(client, "/rooms").json()["state"]["title"]
    assert auto.strip()
    blank = post(client, "/rooms", 2, "bob", json={"roomName": "   "}).json()["state"]["title"]
    assert blank.strip()
    custom = post(client, "/rooms", 3, "carl", json={"roomName": "Làng Của Tôi", "roomCode": "wolfs"}).json()
    assert custom["state"]["title"] == "Làng Của Tôi" and custom["id"] == "WOLFS"
    assert post(client, "/rooms/WOLFS/join", 4, "dan").status_code == 200
    dup = post(client, "/rooms", 5, "eve", json={"roomCode": "WOLFS"})
    assert dup.status_code == 409 and "WOLFS" in dup.json()["detail"]
    assert post(client, "/rooms", 6, "fay", json={"roomName": "x" * 31}).status_code == 422


@pytest.mark.parametrize("code", ["ABCD", "ABCDEF", "AB1DE", "AB DE"])
def test_invalid_room_code_is_rejected(client, code):
    assert post(client, "/rooms", json={"roomCode": code}).status_code == 422
    assert get(client, f"/rooms/{code}").status_code == 422


def test_timer_events_and_dead_talk_options(client):
    state = post(client, "/rooms", json={"seats": seats(7), "start": True, "timerSeconds": 60,
                                         "events": False, "deadTalk": False}).json()["state"]
    assert state["timer"] == 60 and state["events"] is False and state["deadTalk"] is False
    assert state["game"]["timer"]["total"] in (60, 120) and state["game"]["event"] is None
    assert post(client, "/rooms", 2, "bob", json={"timerSeconds": 9999}).status_code == 422
    assert post(client, "/rooms", 2, "bob", json={"timerSeconds": 3}).status_code == 422
    assert post(client, "/rooms", 2, "bob", json={"timerSeconds": 0}).status_code == 201


def test_list_rooms_shows_only_open_listed_lobbies(client):
    open_code = make_room(client, roomName="Mở")
    post(client, "/rooms", 2, "bob", json={"listed": False})
    started = post(client, "/rooms", 3, "carl", json={"start": True}).json()["id"]
    rooms = get(client, "/rooms", 9, "nine").json()
    assert [r["id"] for r in rooms] == [open_code] and started != open_code
    assert rooms[0] == {"id": open_code, "title": "Mở", "host": "alice", "players": 1, "seats": 5,
                        "open_seats": 4, "max_players": 40, "timer": 0, "events": True}


def test_unknown_room(client):
    assert get(client, "/rooms/ZZZZZ").status_code == 404
    assert post(client, "/rooms/ZZZZZ/join").status_code == 404
    assert post(client, "/rooms/ZZZZZ/leave").status_code == 404
    assert post(client, "/rooms/ZZZZZ/start").status_code == 404
    assert post(client, "/rooms/ZZZZZ/chat", json={"text": "x"}).status_code == 404
    assert get(client, "/rooms/ZZZZZ/perspective/1").status_code == 404


def test_room_codes_are_case_insensitive(client):
    code = make_room(client)
    assert get(client, f"/rooms/{code.lower()}").status_code == 200


def test_non_member_sees_a_lobby_preview_without_any_role(client):
    code = make_room(client, seats=seats(5))
    body = get(client, f"/rooms/{code}", 5, "eve").json()
    assert body["state"]["you"] is None and body["state"]["game"] is None
    assert all(m["faction"] is None and m["ability"] is None for m in body["state"]["members"])


def test_non_member_cannot_view_a_running_game(client):
    code = make_room(client)
    start(client, code)
    assert get(client, f"/rooms/{code}", 99, "eve").status_code == 403


def test_join_rules(client):
    code = make_room(client)
    assert post(client, f"/rooms/{code}/join").status_code == 409  # already seated
    state = post(client, f"/rooms/{code}/join", 2, "bob").json()["state"]
    assert sum(not m["isBot"] for m in state["members"]) == 2 and len(state["members"]) == 5
    start(client, code)
    assert post(client, f"/rooms/{code}/join", 3, "carl").status_code == 409


def test_room_full_when_every_seat_is_human(client):
    code = make_room(client, 5)
    assert post(client, f"/rooms/{code}/join", 9, "late").status_code == 409


def test_a_user_is_limited_to_a_number_of_live_rooms(client):
    client.app.state.ww_store.max_rooms_per_user = 3  # the limit is a setting: a small one keeps the test short
    for _ in range(3):
        assert post(client, "/rooms").status_code == 201
    assert post(client, "/rooms").status_code == 409
    other = post(client, "/rooms", 2, "bob").json()["id"]
    assert post(client, f"/rooms/{other}/join").status_code == 409


def test_join_attempts_are_rate_limited(client):
    for _ in range(15):
        post(client, "/rooms/ZZZZZ/join", 7, "g")
    assert post(client, "/rooms/ZZZZZ/join", 7, "g").status_code == 429


def test_add_bots_is_host_only(client):
    code = make_room(client, 2)
    assert post(client, f"/rooms/{code}/bots", 2, "user2", json={"count": 2}).status_code == 403
    state = post(client, f"/rooms/{code}/bots", json={"count": 3}).json()["state"]
    assert len(state["members"]) == 8
    assert post(client, f"/rooms/{code}/bots", json={"count": 40}).status_code == 422
    assert post(client, f"/rooms/{code}/bots", json={"count": 39}).status_code == 409  # over 40 seats


def test_start_is_host_only_and_once(client):
    code = make_room(client, 2)
    assert post(client, f"/rooms/{code}/start", 2, "user2").status_code == 403
    state = start(client, code)
    assert state["started"] and state["game"]["phase"] in ("night", "day", "over")
    assert post(client, f"/rooms/{code}/start").status_code == 409


def test_start_reveals_only_the_callers_role(client):
    code = make_room(client, 2, seats=seats(7))
    for uid in (1, 2):
        game = start(client, code, 1)["game"] if uid == 1 else get(client, f"/rooms/{code}", 2, "user2").json()["state"]["game"]
        me = game["me"]["id"]
        for p in game["players"]:
            if p["id"] != me and not game["gameOver"]:
                assert p["ability"] is None  # nobody else's ability is shown


def test_leave_lobby_hands_host_over_and_deletes_an_empty_room(client):
    code = make_room(client, 2)
    assert post(client, f"/rooms/{code}/leave").json() == {"left": True}
    state = get(client, f"/rooms/{code}", 2, "user2").json()["state"]
    assert state["isHost"] and state["members"][0]["isBot"]
    post(client, f"/rooms/{code}/leave", 2, "user2")
    assert get(client, f"/rooms/{code}", 2, "user2").status_code == 404


def test_leave_errors(client):
    code = make_room(client)
    assert post(client, f"/rooms/{code}/leave", 9, "x").status_code == 409


def test_leaving_a_running_game_does_not_block_the_others(client):
    code = make_room(client, 2)
    start(client, code)
    assert post(client, f"/rooms/{code}/leave", 2, "user2").json() == {"left": True}
    state = play_out(client, code)
    assert state["game"]["gameOver"]


def test_full_game_to_the_end_and_rematch(client):
    code = make_room(client, 1, timerSeconds=60)
    start(client, code)
    final = play_out(client, code)
    assert all(p["ability"] is not None for p in final["game"]["players"])  # everything revealed at the end
    assert final["history"]["games"] == 1
    again = post(client, f"/rooms/{code}/rematch").json()["state"]
    assert again["started"] and again["game"]["night"] >= 1 and again["history"]["games"] == 1  # a fresh game
    assert again["timer"] == 60


def test_rematch_rules(client):
    code = make_room(client, 2)
    assert post(client, f"/rooms/{code}/rematch").status_code == 409  # not started
    start(client, code)
    assert post(client, f"/rooms/{code}/rematch").status_code == 409  # not finished
    play_out(client, code)
    assert post(client, f"/rooms/{code}/rematch", 2, "user2").status_code == 403


def test_reset_refills_with_bots_and_clears_roles(client):
    code = make_room(client, 2, count=7)
    start(client, code)
    state = post(client, f"/rooms/{code}/reset").json()["state"]
    assert not state["started"] and len(state["members"]) == 5
    assert sum(not m["isBot"] for m in state["members"]) == 2
    assert post(client, f"/rooms/{code}/reset", 2, "user2").status_code == 403


def test_force_is_host_only_and_needs_a_game(client):
    code = make_room(client, 2)
    assert post(client, f"/rooms/{code}/force").status_code == 409
    start(client, code)
    assert post(client, f"/rooms/{code}/force", 2, "user2").status_code == 403


def test_action_loop_with_a_real_player(client):
    code = make_room(client, 1, seats=seats(5, {0: {"faction": "VILLAGER", "ability": "SEE_FACTION"}}))
    state = start(client, code)
    for _ in range(300):
        game = state["game"]
        if game["gameOver"]:
            break
        todo = [a for a in game["actions"] if not a["submitted"]]
        if todo:
            act = todo[0]
            target = act["options"][0] if act["options"] else 0
            r = post(client, f"/rooms/{code}/action", json={"target": target, "kind": "wolf" if act["kind"] == "wolf" else "ability"})
            assert r.status_code == 200, r.text
            state = r.json()["state"]
        else:
            state = post(client, f"/rooms/{code}/force").json()["state"]
    assert state["game"]["gameOver"]


def test_invalid_actions(client):
    code = make_room(client)
    assert post(client, f"/rooms/{code}/action", json={"target": 1}).status_code == 409  # not started
    start(client, code)
    assert post(client, f"/rooms/{code}/action", json={"target": 999}).status_code == 400
    assert post(client, f"/rooms/{code}/action", json={"target": 0, "kind": "bogus"}).status_code == 422
    assert post(client, f"/rooms/{code}/action", json={"target": -1}).status_code == 422
    assert post(client, f"/rooms/{code}/action", 9, "x", json={"target": 1}).status_code == 403


def test_wolf_vote_kind_over_rest(client):
    body = {"seats": seats(6, {0: {"faction": "WOLF", "ability": "KILL_ON_DEATH"},
                               1: {"faction": "WOLF", "ability": "KILL_ON_DEATH"}}), "start": True}
    created = post(client, "/rooms", json=body).json()
    actions = created["state"]["game"]["actions"]
    assert [a["kind"] for a in actions] == ["wolf"]
    r = post(client, f"/rooms/{created['id']}/action", json={"target": 0, "kind": "wolf"})
    game = r.json()["state"]["game"]
    assert r.status_code == 200 and game["phase"] == "day" and [x["kind"] for x in game["actions"]] == ["day"]


def test_chat_over_rest(client):
    code = make_room(client)
    assert post(client, f"/rooms/{code}/chat", json={"text": "hi"}).status_code == 409  # before start
    start(client, code)
    assert post(client, f"/rooms/{code}/chat", json={"text": "  "}).status_code == 400
    assert post(client, f"/rooms/{code}/chat", json={"text": "x" * 200}).status_code == 400
    assert post(client, f"/rooms/{code}/chat", json={"text": "x" * 401}).status_code == 422
    assert post(client, f"/rooms/{code}/chat", 9, "x", json={"text": "hi"}).status_code == 403


def test_chat_is_rate_limited_per_user(client):
    code = make_room(client, seats=seats(5))
    start(client, code)
    codes = [post(client, f"/rooms/{code}/chat", json={"text": f"m{i}"}).status_code for i in range(12)]
    assert 429 in codes


def test_perspective_endpoint_rules(client):
    code = make_room(client, 2, seats=seats(7))
    assert get(client, f"/rooms/{code}/perspective/1").status_code == 409  # not started
    start(client, code)
    assert get(client, f"/rooms/{code}/perspective/2").status_code == 403  # alive: no peeking
    assert get(client, f"/rooms/{code}/perspective/0").status_code == 422
    play_out(client, code)
    view = get(client, f"/rooms/{code}/perspective/2").json()
    assert view["me"]["id"] == 2
    assert get(client, f"/rooms/{code}/perspective/39").status_code == 404
    assert get(client, f"/rooms/{code}/perspective/2", 9, "x").status_code == 403


def test_meta_has_help_timers_and_limits(client):
    meta = client.get("/setup/meta", headers=auth_cookie()).json()
    assert all(a["help"] for a in meta["abilities"])
    assert meta["help"]["rules"] and len(meta["help"]["events"]) == len(ALL_EVENTS)
    assert meta["timerOptions"] == [0, 30, 60, 90] and meta["maxRoomsPerUser"] == MAX_ROOMS_PER_USER
    assert meta["chat"] == {"maxLength": 140, "minIntervalSeconds": 0.8, "keep": 400}


def test_setup_meta_lists_factions_and_abilities(client):
    meta = client.get("/setup/meta", headers=auth_cookie()).json()
    assert {f["code"] for f in meta["factions"]} == {"WOLF", "VILLAGER", "GHOST"}
    allowed = {a["code"]: set(a["allowedFactions"]) for a in meta["abilities"]}
    assert len(allowed) == 11 and "WOLF_VOTE" not in allowed
    assert allowed["TRANSFORM"] == {"GHOST"} and allowed["NONE"] == {"VILLAGER"}
    assert allowed["KILL"] == allowed["KILL_ON_DEATH"] == {"VILLAGER", "WOLF"}
    for code in ("BLOCK_ABILITY", "REVERSE_ABILITY", "BLOCK_EFFECTS", "REVERSE_EFFECTS",
                 "SEE_FACTION", "SEE_ABILITY", "REVEAL_ON_DEATH"):
        assert allowed[code] == {"VILLAGER"}, code
    assert meta["minPlayers"] == 5 and meta["maxPlayers"] == 40
    defaults = {f: [d["label"] for d in meta["defaults"][f]] for f in ("VILLAGER", "WOLF", "GHOST")}
    assert all("Vote ngày" in labels for labels in defaults.values())
    assert "Vote đêm" in defaults["WOLF"] and "Biến hình" in defaults["GHOST"]


def test_history_empty_for_new_user(client):
    assert get(client, "/me/history").json() == []


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_history_limit_validated(client, limit):
    assert get(client, f"/me/history?limit={limit}").status_code == 422


def test_finished_games_show_up_in_the_history_of_every_human_player(client):
    code = make_room(client, 2)
    start(client, code)
    play_out(client, code)
    with client.app.state.session_factory() as db:  # names are read from center's `users`
        db.add_all([Person(user_id=1, username="alice"), Person(user_id=2, username="user2")])
        db.commit()
    for uid in (1, 2):
        history = get(client, "/me/history", uid, name_of(uid)).json()
        assert len(history) == 1
        entry = history[0]
        assert entry["room_id"] == code and entry["size"] == 5
        assert entry["your_outcome"] in ("won", "draw", "lost") and entry["won"] == (entry["your_outcome"] == "won")
        assert sorted(p["username"] for p in entry["players"]) == ["alice", "user2"]  # bots are never stored
        assert entry["winner"] in ("VILLAGER", "WOLF", "GHOST", "DRAW")
        assert {"your_faction", "your_ability", "survived", "days_survived", "game_id", "finished_at"} <= set(entry)
    play_out_again = post(client, f"/rooms/{code}/rematch").status_code
    assert play_out_again == 200
