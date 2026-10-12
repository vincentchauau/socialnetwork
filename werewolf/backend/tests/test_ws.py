import json
import time
from contextlib import ExitStack

import pytest
from starlette.websockets import WebSocketDisconnect

from app import ws as ws_module
from sn_shared import COOKIE_NAME, create_token
from tests.conftest import ALLOWED_ORIGIN, ws_headers
from tests.test_api import get, make_room, post


def start_room(client, players: int = 5) -> tuple[str, dict[int, str]]:
    room_id = make_room(client, players)
    assert post(client, f"/rooms/{room_id}/start").status_code == 200
    roles = {}
    for uid in range(1, players + 1):
        name = "alice" if uid == 1 else f"user{uid}"
        roles[uid] = get(client, f"/rooms/{room_id}", uid, name).json()["state"]["you"]["role"]
    return room_id, roles


def name_of(uid: int) -> str:
    return "alice" if uid == 1 else f"user{uid}"


def open_all(client, stack: ExitStack, room_id: str, ids: list[int]) -> dict[int, object]:
    sockets = {}
    for uid in ids:
        sockets[uid] = stack.enter_context(
            client.websocket_connect(f"/ws/{room_id}", headers=ws_headers(uid, name_of(uid)))
        )
        assert sockets[uid].receive_json()["type"] == "state"
    return sockets


def wait_state(socket, predicate=lambda s: True) -> dict:
    while True:
        frame = socket.receive_json()
        if frame["type"] == "state" and predicate(frame["state"]):
            return frame["state"]


def by_role(roles: dict[int, str], role: str) -> list[int]:
    return [uid for uid, r in roles.items() if r == role]


# ---- connection rules ----

def test_ws_without_cookie_is_rejected(client):
    room_id, _ = start_room(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{room_id}", headers={"Origin": ALLOWED_ORIGIN}):
            pass


@pytest.mark.parametrize("origin", ["http://evil.example", None])
def test_ws_foreign_or_missing_origin_is_rejected(client, origin):
    room_id, _ = start_room(client)
    headers = ws_headers()
    if origin is None:
        del headers["Origin"]
    else:
        headers["Origin"] = origin
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{room_id}", headers=headers):
            pass


def test_ws_non_member_unknown_room_and_bad_name_rejected(client):
    room_id, _ = start_room(client)
    for path, user in [(f"/ws/{room_id}", 99), ("/ws/missing", 1), ("/ws/bad room!", 1)]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(path, headers=ws_headers(user, "x")):
                pass


def test_ws_invalid_token_rejected(client):
    room_id, _ = start_room(client)
    headers = {"Cookie": f"{COOKIE_NAME}=garbage", "Origin": ALLOWED_ORIGIN}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{room_id}", headers=headers):
            pass


def test_ws_closes_when_token_expires(client):
    room_id, _ = start_room(client)
    token = create_token(1, "alice", ttl_seconds=1)
    headers = {"Cookie": f"{COOKIE_NAME}={token}", "Origin": ALLOWED_ORIGIN}
    with client.websocket_connect(f"/ws/{room_id}", headers=headers) as socket:
        socket.receive_json()
        time.sleep(1.2)
        with pytest.raises(WebSocketDisconnect) as info:
            socket.receive_json()
    assert info.value.code == 1008


def test_oversized_frame_closes_connection(client):
    room_id, _ = start_room(client)
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as socket:
        socket.receive_json()
        socket.send_text("x" * (ws_module.MAX_FRAME_CHARS + 1))
        with pytest.raises(WebSocketDisconnect) as info:
            socket.receive_json()
    assert info.value.code == 1009


def test_rate_limit_closes_connection(client, monkeypatch):
    monkeypatch.setattr(ws_module, "RATE_LIMIT_MESSAGES", 3)
    room_id, _ = start_room(client)
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as socket:
        socket.receive_json()
        for _ in range(3):
            socket.send_text("{}")
            socket.receive_json()
        socket.send_text("{}")
        with pytest.raises(WebSocketDisconnect) as info:
            socket.receive_json()
    assert info.value.code == 1008


@pytest.mark.parametrize(
    "payload",
    ["not json", "[]", {"type": "nope"}, {"type": "action"}, {"type": "action", "target": 0},
     {"type": "action", "target": "x"}, {"type": "vote", "target": -4},
     {"type": "chat", "content": ""}, {"type": "chat", "content": "   "},
     {"type": "chat", "content": "x" * 501}],
)
def test_invalid_messages_return_error_and_keep_connection(client, payload):
    room_id, _ = start_room(client)
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as socket:
        socket.receive_json()
        socket.send_text(payload if isinstance(payload, str) else json.dumps(payload))
        assert socket.receive_json()["type"] == "error"
        socket.send_json({"type": "vote", "target": None})  # valid shape, wrong phase
        assert socket.receive_json()["type"] == "error"


def test_binary_frame_gets_error(client):
    room_id, _ = start_room(client)
    with client.websocket_connect(f"/ws/{room_id}", headers=ws_headers()) as socket:
        socket.receive_json()
        socket.send_bytes(b"\x00")
        assert socket.receive_json()["type"] == "error"


def test_lobby_members_can_connect_and_chat(client):
    room_id = make_room(client, 2)
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, [1, 2])
        sockets[2].send_json({"type": "chat", "content": "hi all", "username": "admin"})
        for uid in (1, 2):
            frame = sockets[uid].receive_json()
            assert frame["type"] == "chat" and frame["username"] == "user2"
            assert frame["content"] == "hi all" and frame["scope"] == "all"


# ---- secrecy ----

def visible_roles(state: dict) -> dict[int, str]:
    return {p["id"]: p["role"] for p in state["players"] if p["role"]}


def test_initial_views_never_leak_other_roles(client):
    room_id, roles = start_room(client, 8)
    wolves = set(by_role(roles, "werewolf"))
    for uid in roles:
        state = get(client, f"/rooms/{room_id}", uid, name_of(uid)).json()["state"]
        expected = {uid} | (wolves if uid in wolves else set())
        assert set(visible_roles(state)) == expected
        assert state["you"]["role"] == roles[uid]


def test_every_pushed_frame_is_redacted_through_a_night(client):
    room_id, roles = start_room(client)
    wolf, seer, doctor = (by_role(roles, r)[0] for r in ("werewolf", "seer", "doctor"))
    victim = by_role(roles, "villager")[0]
    frames: list[tuple[int, dict]] = []
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, list(roles))
        sockets[wolf].send_json({"type": "action", "target": victim})
        sockets[seer].send_json({"type": "action", "target": wolf})
        sockets[doctor].send_json({"type": "action", "target": victim})
        for uid, socket in sockets.items():
            while True:
                frame = socket.receive_json()
                frames.append((uid, frame["state"]))
                if frame["state"]["phase"] == "day":
                    break
    for uid, state in frames:
        assert set(visible_roles(state)) == {uid} | ({wolf} if uid == wolf else set())
        if uid != seer:
            assert "inspections" not in state["you"]
        if uid != doctor:
            assert "blocked_target" not in state["you"]


def test_seer_gets_private_result_and_nobody_else_does(client):
    room_id, roles = start_room(client)
    wolf, seer, doctor = (by_role(roles, r)[0] for r in ("werewolf", "seer", "doctor"))
    villagers = by_role(roles, "villager")
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, list(roles))
        sockets[wolf].send_json({"type": "action", "target": villagers[0]})
        sockets[seer].send_json({"type": "action", "target": wolf})
        sockets[doctor].send_json({"type": "action", "target": villagers[0]})
        states = {uid: wait_state(s, lambda st: st["phase"] == "day") for uid, s in sockets.items()}
    assert states[seer]["you"]["inspections"] == [{"id": wolf, "is_werewolf": True}]
    for uid, state in states.items():
        if uid != seer:
            assert "inspections" not in state["you"]
            roles_seen = {p["id"]: p["role"] for p in state["players"] if p["role"]}
            expected = {uid} | ({wolf} if uid == wolf else set())
            assert set(roles_seen) == expected  # protected victim: no death, no reveal


# ---- chat ----

def test_wolf_night_chat_is_private_and_day_chat_is_public(client):
    room_id, roles = start_room(client, 8)
    wolves = by_role(roles, "werewolf")
    others = [u for u in roles if u not in wolves]
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, list(roles))
        sockets[others[0]].send_json({"type": "chat", "content": "psst"})
        assert sockets[others[0]].receive_json()["type"] == "error"
        sockets[wolves[0]].send_json({"type": "chat", "content": "kill bob"})
        for wolf in wolves:
            frame = sockets[wolf].receive_json()
            assert frame["scope"] == "wolves" and frame["content"] == "kill bob"
        # a non-wolf gets nothing: the next frame it sees is the state from the next action
        sockets[wolves[0]].send_json({"type": "vote", "target": others[0]})
        assert sockets[wolves[0]].receive_json()["type"] == "error"
        sockets[others[1]].send_json({"type": "advance"})
        assert sockets[others[1]].receive_json()["type"] == "error"  # not host (host is user 1)
        sockets[1].send_json({"type": "advance"})
        for uid, socket in sockets.items():
            state = wait_state(socket, lambda s: s["phase"] == "day")
            assert state["you"]["chat"] in ("all", None)
        speaker = next(u for u in roles if u != wolves[0] or True)
        sockets[speaker].send_json({"type": "chat", "content": "good morning"})
        for socket in sockets.values():
            frame = socket.receive_json()
            assert frame["scope"] == "all" and frame["username"] == name_of(speaker)


def test_dead_player_cannot_chat_or_act(client):
    room_id, roles = start_room(client)
    wolf = by_role(roles, "werewolf")[0]
    victim = by_role(roles, "villager")[0]
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, list(roles))
        sockets[wolf].send_json({"type": "action", "target": victim})
        sockets[1].send_json({"type": "advance"})
        wait_state(sockets[victim], lambda s: s["phase"] == "day" and not s["you"]["alive"])
        sockets[victim].send_json({"type": "chat", "content": "boo"})
        assert sockets[victim].receive_json()["type"] == "error"
        sockets[victim].send_json({"type": "vote", "target": wolf})
        assert sockets[victim].receive_json()["type"] == "error"


# ---- full game + persistence ----

def test_full_game_finishes_and_is_persisted_in_history(client):
    room_id, roles = start_room(client)
    wolf, seer, doctor = (by_role(roles, r)[0] for r in ("werewolf", "seer", "doctor"))
    villagers = by_role(roles, "villager")
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, list(roles))
        sockets[wolf].send_json({"type": "action", "target": villagers[0]})
        sockets[seer].send_json({"type": "action", "target": wolf})
        sockets[doctor].send_json({"type": "action", "target": doctor})
        wait_state(sockets[1], lambda s: s["phase"] == "day")
        sockets[1].send_json({"type": "advance"})
        wait_state(sockets[1], lambda s: s["phase"] == "vote")
        living = [u for u in roles if u != villagers[0]]
        for uid in living:
            target = wolf if uid != wolf else seer
            sockets[uid].send_json({"type": "vote", "target": target})
        final = wait_state(sockets[1], lambda s: s["phase"] == "finished")
    assert final["winner"] == "village"
    assert all(p["role"] for p in final["players"])
    history = get(client, "/me/history", 1, "alice").json()
    assert len(history) == 1
    entry = history[0]
    assert entry["winner"] == "village" and entry["room_id"] == room_id
    assert entry["your_role"] == roles[1]
    assert entry["won"] == (roles[1] != "werewolf")
    assert {p["username"] for p in entry["players"]} == {name_of(u) for u in roles}
    assert {p["role"] for p in entry["players"]} >= {"werewolf", "seer", "doctor"}
    other = get(client, "/me/history", 99, "stranger").json()
    assert other == []
    # finished rooms do not trap players
    assert post(client, "/rooms", 1, "alice").status_code == 201


def test_leaving_running_game_closes_socket_and_game_continues(client):
    room_id, roles = start_room(client)
    leaver = by_role(roles, "villager")[0]
    with ExitStack() as stack:
        sockets = open_all(client, stack, room_id, list(roles))
        assert post(client, f"/rooms/{room_id}/leave", leaver, name_of(leaver)).status_code == 200
        other = next(u for u in roles if u != leaver)
        state = wait_state(sockets[other], lambda s: len(s["players"]) == 4)
        assert all(p["id"] != leaver for p in state["players"])
        with pytest.raises(WebSocketDisconnect):
            sockets[leaver].receive_json()
