"""The owner's commands in the box of a room do what the buttons of the row do, and nobody else gets them."""

from api.chat import room_commands
from tests.chat.test_assistant import write
from tests.chat.test_room_api import call
from tests.chat.test_virtual_reply import cookie


def say(client, slug, text, uid=1, name="alice"):
    with client.websocket_connect(f"/ws/{slug}", headers=cookie(uid, name)) as socket:
        socket.receive_json()
        socket.send_json({"content": text})
        frames = []
        for _ in range(10):
            frame = socket.receive_json()
            frames.append(frame)
            if frame.get("type") in ("error", "member", "room"):  # the answer: a refusal, or the event of the change
                break
    return frames


def make_room(client):
    call(client, "POST", "/rooms", 1, "alice", json={"slug": "cmds", "title": "Cmds", "visibility": "public"})
    call(client, "POST", "/rooms/cmds/join", 2, "bob", json={})


def status_of(client, user_id):
    people = call(client, "GET", "/rooms/cmds/members", 1, "alice").json()
    return next(p for p in people if p["user_id"] == user_id)


def test_parse():
    assert room_commands.parse("/mute bob") == ("mute", "bob")
    assert room_commands.parse("/ban @Bob") == ("ban", "Bob")
    assert room_commands.parse("/close") == ("close", "")
    assert room_commands.parse("/market lamp") is None and room_commands.parse("hello") is None


def test_the_owner_mutes_unmutes_bans_unbans_and_closes_from_the_box(raw_client):
    make_room(raw_client)
    say(raw_client, "cmds", "/mute bob")
    assert status_of(raw_client, 2)["muted"] is True
    say(raw_client, "cmds", "/unmute bob")
    assert status_of(raw_client, 2)["muted"] is False
    say(raw_client, "cmds", "/ban bob")
    assert status_of(raw_client, 2)["status"] == "banned"
    say(raw_client, "cmds", "/unban bob")
    assert status_of(raw_client, 2)["status"] == "joined"
    say(raw_client, "cmds", "/close")
    assert call(raw_client, "GET", "/rooms/cmds", 1, "alice").json()["state"] == "closed"
    say(raw_client, "cmds", "/reopen")
    assert call(raw_client, "GET", "/rooms/cmds", 1, "alice").json()["state"] == "open"


def test_the_owner_hands_the_room_over_and_a_member_cannot(raw_client):
    make_room(raw_client)
    assert say(raw_client, "cmds", "/kick alice", 2, "bob")[-1]["type"] == "error"  # not the owner: the route refuses
    say(raw_client, "cmds", "/owner bob")
    assert call(raw_client, "GET", "/rooms/cmds", 2, "bob").json()["me"]["role"] == "owner"


def test_a_name_that_is_not_in_the_room_is_told(raw_client):
    make_room(raw_client)
    assert "nobody" in say(raw_client, "cmds", "/mute nobody")[-1]["error"]


def test_parse_saying():
    assert room_commands.parse_saying("Chuyển owner cho Giang Le") == ("owner", "Giang Le")
    assert room_commands.parse_saying("chuyển quyền chủ phòng sang bob nhé") == ("owner", "bob")
    assert room_commands.parse_saying("mời Bob ra khỏi phòng") == ("kick", "Bob")
    assert room_commands.parse_saying("tắt tiếng bob") == ("mute", "bob") and room_commands.parse_saying("đóng phòng đi") == ("close", "")
    assert room_commands.parse_saying("hello there") is None and room_commands.parse_saying("/mute bob") is None


def test_the_owner_talks_the_command_and_a_member_just_chats(raw_client):
    make_room(raw_client)
    with raw_client.websocket_connect("/ws/cmds", headers=cookie(2, "bob")) as socket:  # not the owner: an ordinary message, nobody is muted
        socket.receive_json()
        socket.send_json({"content": "tắt tiếng alice"})
        while (frame := socket.receive_json()).get("type") != "message":
            pass
        assert frame["content"] == "tắt tiếng alice"
    say(raw_client, "cmds", "tắt tiếng bob")
    assert status_of(raw_client, 2)["muted"] is True
    say(raw_client, "cmds", "Chuyển owner cho Bob")
    assert call(raw_client, "GET", "/rooms/cmds", 2, "bob").json()["me"]["role"] == "owner"
