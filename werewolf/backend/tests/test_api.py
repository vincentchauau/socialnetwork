import pytest

from tests.conftest import auth_cookie


def post(client, path, user=1, name="alice"):
    return client.post(path, headers=auth_cookie(user, name))


def get(client, path, user=1, name="alice"):
    return client.get(path, headers=auth_cookie(user, name))


def make_room(client, players: int = 1) -> str:
    room_id = post(client, "/rooms").json()["id"]
    for uid in range(2, players + 1):
        assert post(client, f"/rooms/{room_id}/join", uid, f"user{uid}").status_code == 200
    return room_id


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method,path",
    [("post", "/rooms"), ("get", "/rooms"), ("get", "/rooms/abc"), ("post", "/rooms/abc/join"),
     ("post", "/rooms/abc/leave"), ("post", "/rooms/abc/start"), ("get", "/me/history")],
)
def test_routes_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_create_room_makes_caller_host_with_short_id(client):
    response = post(client, "/rooms")
    assert response.status_code == 201
    body = response.json()
    assert 1 <= len(body["id"]) <= 32
    assert body["state"]["phase"] == "lobby" and body["state"]["host_id"] == 1
    assert body["state"]["players"][0]["username"] == "alice"


def test_room_ids_are_unique_and_unguessable(client):
    ids = set()
    for uid in range(1, 6):
        ids.add(post(client, "/rooms", uid, f"u{uid}").json()["id"])
    assert len(ids) == 5


def test_user_cannot_create_second_unfinished_room(client):
    post(client, "/rooms")
    assert post(client, "/rooms").status_code == 409


def test_list_rooms_shows_only_open_lobbies(client):
    open_room = make_room(client)
    started = post(client, "/rooms", 20, "zed").json()["id"]
    for uid in range(21, 25):
        post(client, f"/rooms/{started}/join", uid, f"u{uid}")
    assert post(client, f"/rooms/{started}/start", 20, "zed").status_code == 200
    rooms = get(client, "/rooms", 9, "nine").json()
    assert [r["id"] for r in rooms] == [open_room]
    assert rooms[0] == {"id": open_room, "host": "alice", "players": 1, "max_players": 12}


def test_get_room_unknown_and_invalid_id(client):
    assert get(client, "/rooms/nope").status_code == 404
    assert get(client, "/rooms/bad room!").status_code == 422
    assert get(client, "/rooms/" + "x" * 33).status_code == 422


def test_non_member_can_view_lobby_without_you(client):
    room_id = make_room(client)
    body = get(client, f"/rooms/{room_id}", 5, "eve").json()
    assert body["state"]["you"] is None


def test_non_member_cannot_view_running_game(client):
    room_id = make_room(client, 5)
    post(client, f"/rooms/{room_id}/start")
    assert get(client, f"/rooms/{room_id}", 99, "eve").status_code == 403


def test_join_rules(client):
    room_id = make_room(client)
    assert post(client, f"/rooms/{room_id}/join", 1, "alice").status_code == 409
    assert post(client, "/rooms/nope/join", 2, "bob").status_code == 404
    other = post(client, "/rooms", 30, "carl").json()["id"]
    assert post(client, f"/rooms/{room_id}/join", 30, "carl").status_code == 409
    assert other


def test_room_capacity_is_twelve(client):
    room_id = make_room(client, 12)
    assert post(client, f"/rooms/{room_id}/join", 99, "late").status_code == 409


def test_join_after_start_rejected(client):
    room_id = make_room(client, 5)
    post(client, f"/rooms/{room_id}/start")
    assert post(client, f"/rooms/{room_id}/join", 99, "late").status_code == 409


def test_start_is_host_only_and_needs_five_players(client):
    room_id = make_room(client, 4)
    assert post(client, f"/rooms/{room_id}/start").status_code == 409
    post(client, f"/rooms/{room_id}/join", 5, "user5")
    assert post(client, f"/rooms/{room_id}/start", 2, "user2").status_code == 403
    started = post(client, f"/rooms/{room_id}/start")
    assert started.status_code == 200 and started.json()["state"]["phase"] == "night"
    assert post(client, f"/rooms/{room_id}/start").status_code == 409


def test_start_response_only_reveals_callers_role(client):
    room_id = make_room(client, 5)
    state = post(client, f"/rooms/{room_id}/start").json()["state"]
    others = [p["role"] for p in state["players"] if p["id"] != 1]
    assert state["you"]["role"] is not None
    assert all(role in (None, "werewolf") for role in others)


def test_leave_lobby_transfers_host_and_deletes_empty_room(client):
    room_id = make_room(client, 2)
    assert post(client, f"/rooms/{room_id}/leave").json() == {"left": True}
    state = get(client, f"/rooms/{room_id}", 2, "user2").json()["state"]
    assert state["host_id"] == 2
    post(client, f"/rooms/{room_id}/leave", 2, "user2")
    assert get(client, f"/rooms/{room_id}", 2, "user2").status_code == 404


def test_leave_errors(client):
    room_id = make_room(client)
    assert post(client, f"/rooms/{room_id}/leave", 9, "x").status_code == 409
    assert post(client, "/rooms/nope/leave").status_code == 404


def test_history_empty_for_new_user(client):
    assert get(client, "/me/history").json() == []


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_history_limit_validated(client, limit):
    assert get(client, f"/me/history?limit={limit}").status_code == 422
