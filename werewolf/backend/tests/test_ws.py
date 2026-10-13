import json
from contextlib import ExitStack

import pytest
from starlette.websockets import WebSocketDisconnect

from app import ws as ws_module
from sn_shared import COOKIE_NAME, create_token
from tests.conftest import ALLOWED_ORIGIN, ws_headers
from tests.test_api import get, make_room, name_of, post, seats, start


def connect(client, stack: ExitStack, code: str, uid: int = 1):
    socket = stack.enter_context(client.websocket_connect(f"/ws/{code}", headers=ws_headers(uid, name_of(uid))))
    return socket


def open_state(client, stack, code, uid=1):
    socket = connect(client, stack, code, uid)
    frame = socket.receive_json()
    assert frame["type"] == "state"
    return socket, frame["state"]


def next_frame(socket, kind: str) -> dict:
    while True:
        frame = socket.receive_json()
        if frame["type"] == kind:
            return frame


def expect_closed(client, code, headers, expected=1008):
    with pytest.raises(WebSocketDisconnect) as exc:  # refused before the handshake completes
        with client.websocket_connect(f"/ws/{code}", headers=headers) as socket:
            socket.receive_json()
    assert exc.value.code == expected


# ---- connection rules ----
def test_connect_needs_origin_cookie_membership_and_a_real_room(client):
    code = make_room(client)
    expect_closed(client, code, {**ws_headers(), "Origin": "https://evil.example"})
    expect_closed(client, code, {"Origin": ALLOWED_ORIGIN})
    expect_closed(client, code, {"Cookie": f"{COOKIE_NAME}=garbage", "Origin": ALLOWED_ORIGIN})
    expect_closed(client, code, ws_headers(9, "stranger"))
    expect_closed(client, "ZZZZZ", ws_headers())
    expect_closed(client, "bad code!", ws_headers())
    headers = ws_headers()
    headers.pop("Origin")
    expect_closed(client, code, headers)


def test_member_gets_their_own_state_first(client):
    code = make_room(client, 2, seats=seats(6))
    with ExitStack() as stack:
        _, host_state = open_state(client, stack, code, 1)
        _, guest_state = open_state(client, stack, code, 2)
    assert host_state["you"]["username"] == "alice" and guest_state["you"]["username"] == "user2"
    assert host_state["isHost"] and not guest_state["isHost"]


def test_state_is_pushed_when_the_room_changes(client):
    code = make_room(client)
    with ExitStack() as stack:
        socket, state = open_state(client, stack, code)
        assert not state["started"]
        post(client, f"/rooms/{code}/join", 2, "user2")
        pushed = next_frame(socket, "state")["state"]
        assert "user2" in [m["name"] for m in pushed["members"]]
        post(client, f"/rooms/{code}/start")
        assert next_frame(socket, "state")["state"]["started"]


def test_a_newer_socket_replaces_the_older_one(client):
    code = make_room(client)
    with ExitStack() as stack:
        first, _ = open_state(client, stack, code)
        open_state(client, stack, code)
        with pytest.raises(WebSocketDisconnect) as exc:
            first.receive_json()
    assert exc.value.code == 1008


def test_server_full_refuses_with_try_again_later(client):
    code = make_room(client)
    client.app.state.hub._max_connections = 0
    expect_closed(client, code, ws_headers(), expected=1013)


def test_leaving_the_room_closes_the_socket(client):
    code = make_room(client, 2)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code, 2)
        post(client, f"/rooms/{code}/leave", 2, "user2")
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_deleting_the_room_closes_every_socket(client):
    code = make_room(client)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code)
        post(client, f"/rooms/{code}/leave")
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 1001


# ---- messages ----
def test_bad_frames_get_an_error_not_a_crash(client):
    code = make_room(client)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code)
        for raw in ("not json", "[]", '{"type":"nope"}', '{"type":"action"}', '{"type":"action","target":-1}',
                    '{"type":"action","target":1,"kind":"x"}', '{"type":"chat","text":' + '"x"' * 3 + "}"):
            socket.send_text(raw)
            assert socket.receive_json() == {"type": "error", "error": "Invalid message"}
        socket.send_bytes(b"\x00")
        assert socket.receive_json()["error"] == "Only text frames are supported"


def test_oversized_frame_closes_the_socket(client):
    code = make_room(client)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code)
        socket.send_text(json.dumps({"type": "chat", "text": "x" * (ws_module.MAX_FRAME_CHARS + 1)}))
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 1009


def test_message_flood_closes_the_socket(client):
    code = make_room(client)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code)
        with pytest.raises(WebSocketDisconnect) as exc:
            for _ in range(60):
                socket.send_text('{"type":"force"}')
                socket.receive_json()
    assert exc.value.code == 1008


def test_action_over_the_socket_updates_everyone(client):
    code = make_room(client, 2, seats=seats(7))
    start(client, code)
    with ExitStack() as stack:
        host, hs = open_state(client, stack, code, 1)
        guest, gs = open_state(client, stack, code, 2)
        for socket, state in ((host, hs), (guest, gs)):
            todo = [a for a in state["game"]["actions"] if not a["submitted"]]
            if todo:
                act = todo[0]
                socket.send_json({"type": "action", "target": act["options"][0] if act["options"] else 0,
                                  "kind": "wolf" if act["kind"] == "wolf" else "ability"})
                pushed = next_frame(socket, "state")["state"]
                assert pushed["game"] is not None
        socket.send_json({"type": "action", "target": 999})
        assert next_frame(socket, "error")["error"]


def test_force_over_the_socket_is_host_only(client):
    code = make_room(client, 2, seats=seats(7))
    start(client, code)
    with ExitStack() as stack:
        host, _ = open_state(client, stack, code, 1)
        guest, _ = open_state(client, stack, code, 2)
        guest.send_json({"type": "force"})
        assert "chủ phòng" in next_frame(guest, "error")["error"]
        host.send_json({"type": "force"})
        assert next_frame(host, "state")["state"]["game"]["night"] >= 1


def test_chat_before_the_game_starts_is_an_error(client):
    code = make_room(client)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code)
        socket.send_json({"type": "chat", "text": "hi"})
        assert next_frame(socket, "error")["error"] == "Game chưa bắt đầu"


def test_chat_is_delivered_as_a_message_only_to_who_may_read_it(client):
    roles = [{"faction": "WOLF", "ability": "KILL_ON_DEATH"}, {"faction": "WOLF", "ability": "KILL_ON_DEATH"}] \
        + [{"faction": "VILLAGER", "ability": "NONE"}] * 5
    code = make_room(client, 3, seats=roles)
    state = start(client, code)
    wolves = [uid for uid in (1, 2, 3) if
              get(client, f"/rooms/{code}", uid, name_of(uid)).json()["state"]["game"]["me"]["faction"]["code"] == "WOLF"]
    others = [uid for uid in (1, 2, 3) if uid not in wolves]
    assert state["game"]["phase"] == "night" and wolves and others
    with ExitStack() as stack:
        sockets = {uid: open_state(client, stack, code, uid)[0] for uid in (1, 2, 3)}
        speaker = wolves[0]
        sockets[speaker].send_json({"type": "chat", "text": "giết P7 đi"})
        frame = next_frame(sockets[speaker], "chat")
        assert frame["message"]["text"] == "giết P7 đi" and frame["message"]["channel"] == "wolf"
        assert frame["message"]["author"]["name"] == name_of(speaker)  # the author comes from the seat
        for uid in wolves[1:]:
            assert next_frame(sockets[uid], "chat")["message"]["channel"] == "wolf"
        # a non-wolf receives nothing: the next thing it sees is its own later frame
        sockets[others[0]].send_json({"type": "force"})
        assert sockets[others[0]].receive_json()["type"] == "error"  # nothing was queued before it


def test_chat_over_the_socket_is_rate_limited_and_cleaned(client):
    code = make_room(client, 1, seats=seats(7, {0: {"faction": "WOLF", "ability": "KILL_ON_DEATH"}}))
    start(client, code)
    with ExitStack() as stack:
        socket, _ = open_state(client, stack, code)
        socket.send_json({"type": "chat", "text": "a\x00b‮   <b>c</b>\x07"})
        assert next_frame(socket, "chat")["message"]["text"] == "ab <b>c</b>"  # controls stripped, HTML left as text
        socket.send_json({"type": "chat", "text": "again"})
        assert "nhanh" in next_frame(socket, "error")["error"]  # the engine's 0.8 s spacing
        errors = 0
        for i in range(12):
            socket.send_json({"type": "chat", "text": f"m{i}"})
            frame = socket.receive_json()
            errors += frame["type"] == "error"
        assert errors >= 8
