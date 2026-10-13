import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

import app.main as main_module
import app.presence as presence_module
from app.lobby import Lobby
from app.presence import Presence
from app.rooms import RoomHub
from tests.conftest import auth_cookie, frame_of, next_message, ws_headers


def connect(client, room, uid, name):
    return client.websocket_connect(f"/ws/{room}", headers=ws_headers(uid, name))


def lobby(client, uid=1, name="alice"):
    return client.websocket_connect("/ws-lobby", headers=ws_headers(uid, name))


# ---- presence unit ----

def test_refcount_counts_two_tabs_once():
    presence = Presence()
    assert presence.join("r", 1, "alice") is True
    assert presence.join("r", 1, "alice") is False
    assert presence.members("r") == ([{"userId": 1, "username": "alice"}], 1)
    assert presence.leave("r", 1) is False
    assert presence.leave("r", 1) is True
    assert presence.rooms() == []
    assert presence.leave("r", 1) is False


def test_members_sorted_case_insensitive_and_capped():
    presence = Presence()
    for uid, name in [(1, "bob"), (2, "Alice"), (3, "carol")]:
        presence.join("r", uid, name)
    assert [m["username"] for m in presence.members("r")[0]] == ["Alice", "bob", "carol"]
    big = Presence()
    for uid in range(1, 251):
        big.join("r", uid, f"u{uid:03d}")
    listed, total = big.members("r")
    assert len(listed) == 200 and total == 250


def test_rooms_ordered_by_users_then_name_and_capped():
    presence = Presence()
    presence.join("b", 1, "a")
    presence.join("a", 2, "b")
    presence.join("c", 3, "c")
    presence.join("c", 4, "d")
    assert presence.rooms() == [
        {"room": "c", "users": 2},
        {"room": "a", "users": 1},
        {"room": "b", "users": 1},
    ]
    many = Presence()
    for i in range(150):
        many.join(f"r{i:03d}", i, "x")
    assert len(many.rooms()) == 100


def test_refusals(monkeypatch):
    monkeypatch.setattr(presence_module, "MAX_MEMBERS_PER_ROOM", 1)
    monkeypatch.setattr(presence_module, "MAX_LIVE_ROOMS", 1)
    presence = Presence()
    assert presence.refusal("r", 1) is None
    presence.join("r", 1, "a")
    assert presence.refusal("r", 1) is None  # same user, another tab
    assert presence.refusal("r", 2) == "Room is full"
    assert presence.refusal("other", 2) == "Too many active rooms"


# ---- chat socket ----

def test_join_leave_and_presence_frames(client):
    with connect(client, "g", 1, "alice") as alice:
        assert alice.receive_json()["event"] == "join"
        assert alice.receive_json() == {
            "type": "presence", "room": "g",
            "members": [{"userId": 1, "username": "alice"}], "total": 1,
        }
        with connect(client, "g", 2, "bob"):
            join = alice.receive_json()
            assert join["type"] == "system" and join["event"] == "join"
            assert join["userId"] == 2 and join["username"] == "bob" and join["room"] == "g"
            assert "at" in join
            assert [m["username"] for m in alice.receive_json()["members"]] == ["alice", "bob"]
        leave = alice.receive_json()
        assert (leave["type"], leave["event"], leave["username"]) == ("system", "leave", "bob")
        assert alice.receive_json()["total"] == 1


def test_second_tab_gets_snapshot_without_join_broadcast(client):
    with connect(client, "g", 1, "alice") as tab1:
        frame_of(tab1, "presence")
        with connect(client, "g", 1, "alice") as tab2:
            snapshot = tab2.receive_json()
            assert snapshot["type"] == "presence" and snapshot["total"] == 1
            tab1.send_json({"content": "ping"})
            assert tab1.receive_json()["type"] == "message"  # no join frame came first
        tab1.send_json({"content": "still member"})
        assert tab1.receive_json()["content"] == "still member"  # no leave frame either
        assert client.get("/rooms", headers=auth_cookie()).json() == [{"room": "g", "users": 1}]
    assert client.get("/rooms", headers=auth_cookie()).json() == []


def test_frames_carry_type(client):
    with connect(client, "g", 1, "alice") as alice:
        alice.send_json({"content": "hi"})
        assert next_message(alice)["type"] == "message"
        alice.send_json({"content": ""})
        assert frame_of(alice, "error")["error"]


def test_system_frames_are_not_stored(client):
    with connect(client, "g", 1, "alice") as alice, connect(client, "g", 2, "bob"):
        alice.send_json({"content": "real"})
        next_message(alice)
    history = client.get("/rooms/g/messages", headers=auth_cookie()).json()
    assert [m["content"] for m in history] == ["real"]


def test_member_cap_refuses_with_1013(client, monkeypatch):
    monkeypatch.setattr(presence_module, "MAX_MEMBERS_PER_ROOM", 1)
    with connect(client, "g", 1, "alice"):
        with connect(client, "g", 2, "bob") as bob:
            with pytest.raises(WebSocketDisconnect) as info:
                bob.receive_json()
            assert info.value.code == 1013 and info.value.reason == "Room is full"
        with connect(client, "g", 1, "alice"):  # another tab of a member is fine
            pass


def test_live_room_cap_refuses_with_1013(client, monkeypatch):
    monkeypatch.setattr(presence_module, "MAX_LIVE_ROOMS", 1)
    with connect(client, "a", 1, "alice"):
        with connect(client, "b", 2, "bob") as bob:
            with pytest.raises(WebSocketDisconnect) as info:
                bob.receive_json()
            assert info.value.code == 1013


def test_socket_cap_per_user_across_rooms(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_SOCKETS_PER_USER", 2)
    with connect(client, "a", 1, "alice"), connect(client, "b", 1, "alice"):
        with connect(client, "c", 1, "alice") as third:
            with pytest.raises(WebSocketDisconnect) as info:
                third.receive_json()
            assert info.value.code == 1013
    with connect(client, "c", 1, "alice") as again:  # slots were released
        assert again.receive_json()["event"] == "join"


# ---- REST /rooms ----

def test_rooms_requires_auth(client):
    assert client.get("/rooms").status_code == 401


def test_rooms_lists_live_rooms_by_users(client):
    with connect(client, "quiet", 1, "alice"), connect(client, "busy", 2, "bob"), \
         connect(client, "busy", 3, "carol"):
        assert client.get("/rooms", headers=auth_cookie()).json() == [
            {"room": "busy", "users": 2},
            {"room": "quiet", "users": 1},
        ]


# ---- lobby socket ----

def test_lobby_pushes_snapshot_and_changes(client):
    with lobby(client) as watcher:
        assert watcher.receive_json() == {"type": "rooms", "rooms": []}
        with connect(client, "g", 2, "bob"):
            assert watcher.receive_json() == {"type": "rooms", "rooms": [{"room": "g", "users": 1}]}


def test_lobby_never_exposes_member_names(client):
    with connect(client, "g", 2, "bob"):
        with lobby(client) as watcher:
            assert "bob" not in str(watcher.receive_json())


@pytest.mark.parametrize("headers", [
    {"Origin": "http://localhost:8080"},
    ws_headers(origin="http://evil.example"),
    auth_cookie(),
])
def test_lobby_requires_cookie_and_origin(client, headers):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws-lobby", headers=headers):
            pass


def test_lobby_socket_cap(client):
    with lobby(client), lobby(client):
        with lobby(client) as third:
            with pytest.raises(WebSocketDisconnect) as info:
                third.receive_json()
            assert info.value.code == 1013


def test_lobby_oversized_frame_closes(client):
    with lobby(client) as watcher:
        watcher.receive_json()
        watcher.send_text("x" * (8 * 1024 + 1))
        with pytest.raises(WebSocketDisconnect):
            watcher.receive_json()


def test_lobby_flood_closes(client):
    with lobby(client) as watcher:
        watcher.receive_json()
        for _ in range(60):
            watcher.send_text("x")
        with pytest.raises(WebSocketDisconnect):
            watcher.receive_json()


# ---- lobby coalescing (fake clock) ----

class FakeSocket:
    def __init__(self):
        self.frames = []

    async def send_json(self, payload):
        self.frames.append(payload)


def test_lobby_coalesces_to_leading_push_plus_one_trailing():
    async def scenario():
        now = [100.0]
        slept = []

        async def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds

        presence = Presence()
        hub = RoomHub()
        watcher = FakeSocket()
        hub.add("lobby", watcher)
        board = Lobby(presence, hub, clock=lambda: now[0], sleep=sleep)

        presence.join("a", 1, "x")
        await board.notify()  # leading edge: pushed at once
        assert len(watcher.frames) == 1

        presence.join("b", 2, "y")
        await board.notify()  # inside the interval: deferred
        presence.join("c", 3, "z")
        await board.notify()  # absorbed by the pending push
        assert len(watcher.frames) == 1

        await board._pending
        assert slept == [pytest.approx(0.5)]
        assert len(watcher.frames) == 2
        assert {r["room"] for r in watcher.frames[-1]["rooms"]} == {"a", "b", "c"}

        now[0] += 5
        await board.notify()  # quiet period elapsed: immediate again
        assert len(watcher.frames) == 3
        await board.close()

    asyncio.run(scenario())
