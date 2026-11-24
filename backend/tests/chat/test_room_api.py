from datetime import UTC, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.chat.conftest import ALLOWED_ORIGIN, auth_cookie, frame_of, next_message, ws_headers


# Rooms made by `make` without a way in of their own are rooms with approval (they have an owner who manages them); the people who join
# them in these tests are let in by that owner at once, so a test reads "joined" and not the waiting for an answer. Rooms made with a
# `join_policy` of their own are left as they are: they test that policy.
OWNED: dict[str, tuple[int, str]] = {}


def call(client, method, path, uid=1, name="alice", **kwargs):
    headers = {**auth_cookie(uid, name), "Origin": ALLOWED_ORIGIN}
    response = client.request(method, path, headers=headers, **kwargs)
    parts = path.split("/")
    if method == "POST" and len(parts) == 4 and parts[1] == "rooms" and parts[3] == "join" and parts[2] in OWNED:
        owner_id, owner_name = OWNED[parts[2]]
        if uid != owner_id and response.status_code in (200, 201) and (response.json().get("me") or {}).get("status") == "pending":
            call(client, "PATCH", f"/rooms/{parts[2]}/members/{uid}", owner_id, owner_name, json={"status": "joined"})
            return client.request(method, path, headers=headers, **kwargs)  # joining again says what it is now
    return response


def make(client, uid=1, name="alice", **fields):
    own_policy = "join_policy" in fields
    body = {"title": "Residents", "join_policy": "approval", **fields}
    response = call(client, "POST", "/rooms", uid, name, json=body)
    assert response.status_code == 201, response.text
    if own_policy:
        OWNED.pop(response.json()["slug"], None)
    else:
        OWNED[response.json()["slug"]] = (uid, name)
    return response.json()


def texts(client, slug, uid=1, name="alice"):
    """What people said (the lines about who came and went are `system`)."""
    return [m for m in call(client, "GET", f"/rooms/{slug}/messages", uid, name).json() if m["kind"] == "text"]


def next_text(socket):
    while True:
        message = next_message(socket)
        if message["kind"] == "text":
            return message


def ws(client, slug, uid=1, name="alice"):
    return client.websocket_connect(f"/ws/{slug}", headers=ws_headers(uid, name))


def refused(client, slug, uid=2, name="bob") -> WebSocketDisconnect:
    """The socket is accepted and then closed with the reason: read until it is."""
    with pytest.raises(WebSocketDisconnect) as info:
        with ws(client, slug, uid, name) as socket:
            while True:
                socket.receive_json()
    return info.value


def bring(client, slug, uid, name, owner=(1, "alice")):
    """The owner brings a person in by their id (a hidden room has no other way in); the chat knows a person from their first call."""
    call(client, "GET", "/rooms", uid, name)
    assert call(client, "POST", f"/rooms/{slug}/members", owner[0], owner[1], json={"user_id": uid}).status_code == 201


def iso(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat()


# ---- making a room ----------------------------------------------------------------------------------------------


def test_a_room_gets_an_address_from_its_title_and_its_maker_owns_it(raw_client):
    room = make(raw_client, title="Nhóm Cư Dân Q7")
    assert room["slug"] == "nhom-cu-dan-q7"
    assert room["user_id"] == 1 and room["members"] == 1
    assert room["me"]["role"] == "owner" and room["me"]["status"] == "joined"
    assert room["kind"] == "chat" and room["visibility"] == "public" and room["join_policy"] == "approval"


def test_two_rooms_with_the_same_title_get_different_addresses(raw_client):
    assert make(raw_client)["slug"] == "residents"
    assert make(raw_client)["slug"] == "residents-2"


def test_an_address_can_be_chosen_once(raw_client):
    assert make(raw_client, slug="garage-sale")["slug"] == "garage-sale"
    taken = call(raw_client, "POST", "/rooms", 2, "bob", json={"title": "Other", "slug": "garage-sale"})
    assert taken.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "x" * 81},
        {"title": "ok", "capacity": 1},
        {"title": "ok", "capacity": 201},
        {"title": "ok", "visibility": "secret"},
        {"title": "ok", "slug": "a b"},
        {"title": "ok", "visibility": "private", "join_policy": "open"},
        {"title": "ok", "settings": {"x": 1}},
    ],
)
def test_a_bad_room_is_refused(raw_client, body):
    assert call(raw_client, "POST", "/rooms", json=body).status_code == 422


def test_one_person_can_own_only_so_many_rooms(raw_client):
    for index in range(20):
        make(raw_client, title=f"Room {index}")
    assert call(raw_client, "POST", "/rooms", json={"title": "One too many"}).status_code == 409


def test_writing_needs_a_known_origin_and_a_session(raw_client):
    assert raw_client.post("/rooms", json={"title": "x"}, headers={"Origin": ALLOWED_ORIGIN}).status_code == 401
    assert raw_client.post("/rooms", json={"title": "x"}, headers=auth_cookie()).status_code == 403
    foreign = {**auth_cookie(), "Origin": "http://evil.example"}
    assert raw_client.post("/rooms", json={"title": "x"}, headers=foreign).status_code == 403


# ---- finding rooms ----------------------------------------------------------------------------------------------


def test_the_public_list_shows_public_rooms_by_how_many_members_they_have(raw_client):
    make(raw_client, title="Quiet")
    busy = make(raw_client, title="Busy")
    call(raw_client, "POST", f"/rooms/{busy['slug']}/join", 2, "bob", json={})
    make(raw_client, title="Hidden", visibility="private", join_policy="approval")
    titles = [room["title"] for room in call(raw_client, "GET", "/rooms", 3, "carol").json()]
    assert titles == ["Busy", "Quiet"]


def test_the_list_can_be_searched_and_filtered(raw_client):
    make(raw_client, title="Garage sale Q7", category="garage sale")
    make(raw_client, title="Home buyers", category="buyers")
    found = lambda query: [r["title"] for r in call(raw_client, "GET", "/rooms" + query, 2, "bob").json()]  # noqa: E731
    assert found("?q=garage") == ["Garage sale Q7"]
    assert found("?category=BUYERS") == ["Home buyers"]
    assert found("?q=nothing") == []


def test_mine_lists_the_rooms_i_belong_to_with_what_i_have_not_read(raw_client):
    room = make(raw_client, title="Talk")
    call(raw_client, "POST", f"/rooms/{room['slug']}/join", 2, "bob", json={})
    with ws(raw_client, room["slug"], 1, "alice") as alice:
        alice.send_json({"content": "one"})
        first = next_message(alice)
        alice.send_json({"content": "two"})
        second = next_message(alice)
    mine = call(raw_client, "GET", "/rooms?scope=mine", 2, "bob").json()
    assert [r["slug"] for r in mine] == ["talk"] and mine[0]["me"]["unread"] == 2
    assert call(raw_client, "POST", "/rooms/talk/read", 2, "bob", json={"message_id": first["id"]}).status_code == 204
    assert call(raw_client, "GET", "/rooms?scope=mine", 2, "bob").json()[0]["me"]["unread"] == 1
    call(raw_client, "POST", "/rooms/talk/read", 2, "bob", json={"message_id": second["id"]})
    call(raw_client, "POST", "/rooms/talk/read", 2, "bob", json={"message_id": 1})  # never goes back
    assert call(raw_client, "GET", "/rooms?scope=mine", 2, "bob").json()[0]["me"]["unread"] == 0
    assert call(raw_client, "GET", "/rooms?scope=mine", 1, "alice").json()[0]["me"]["unread"] == 0  # my own do not count


def test_a_private_room_does_not_exist_for_anyone_outside_it(raw_client):
    room = make(raw_client, title="Secret", visibility="private", join_policy="approval")
    for path in ("", "/members", "/messages"):
        assert call(raw_client, "GET", f"/rooms/{room['slug']}{path}", 2, "bob").status_code == 404
    assert call(raw_client, "POST", f"/rooms/{room['slug']}/join", 2, "bob", json={}).status_code == 404
    assert call(raw_client, "GET", "/rooms", 2, "bob").json() == []


# ---- joining ----------------------------------------------------------------------------------------------------


def test_anyone_can_join_an_open_room_and_joining_twice_is_the_same(raw_client):
    room = make(raw_client)
    first = call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert first.status_code == 200 and first.json()["me"]["status"] == "joined" and first.json()["members"] == 2
    assert call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={}).json()["members"] == 2
    assert room["capacity"] == 200


def test_a_room_that_needs_approval_keeps_a_newcomer_waiting_until_the_owner_lets_them_in(raw_client):
    make(raw_client, join_policy="approval")
    waiting = call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={}).json()
    assert waiting["me"]["status"] == "pending" and waiting["members"] == 1
    assert refused(raw_client, "residents").reason == "Waiting for approval"
    pending = [m for m in call(raw_client, "GET", "/rooms/residents/members", 1, "alice").json() if m["status"] == "pending"]
    assert [m["username"] for m in pending] == ["bob"]
    assert [m["username"] for m in call(raw_client, "GET", "/rooms/residents/members", 3, "carol").json()] == ["alice"]  # a request is for the owner
    allowed = call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"status": "joined"})
    assert allowed.status_code == 200
    with ws(raw_client, "residents", 2, "bob") as bob:
        bob.send_json({"content": "thank you"})
        assert next_message(bob)["content"] == "thank you"


def test_a_hidden_room_is_not_there_for_anyone_outside_and_the_owner_brings_people_in(raw_client):
    make(raw_client, join_policy="approval", visibility="private")
    assert call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={}).status_code in (403, 404)  # a private room is not even there for them
    assert call(raw_client, "GET", "/rooms/residents", 2, "bob").status_code == 404
    assert call(raw_client, "POST", "/rooms/residents/members", 1, "alice", json={"username": "bob"}).status_code == 201
    assert call(raw_client, "GET", "/rooms/residents/messages", 2, "bob").status_code == 200
    assert "invite_code" not in call(raw_client, "GET", "/rooms/residents", 1, "alice").json()


def test_a_full_room_takes_nobody_more(raw_client):
    make(raw_client, capacity=2, join_policy="open")
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={}).status_code == 409


def test_a_closed_room_takes_nobody(raw_client):
    make(raw_client, title="Sale", join_policy="open")
    assert call(raw_client, "PATCH", "/rooms/sale", 1, "alice", json={"state": "closed"}).status_code == 200
    assert call(raw_client, "GET", "/rooms/sale", 2, "bob").json()["state"] == "closed"
    assert call(raw_client, "POST", "/rooms/sale/join", 2, "bob", json={}).status_code == 409


def test_leaving_a_room_and_the_owner_passing_it_on(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={})
    assert call(raw_client, "POST", "/rooms/residents/leave", 3, "carol").status_code == 204
    assert call(raw_client, "GET", "/rooms/residents", 1, "alice").json()["members"] == 2
    assert call(raw_client, "POST", "/rooms/residents/leave", 1, "alice").status_code == 409  # the owner chooses who comes next first
    assert call(raw_client, "POST", "/rooms/residents/transfer", 1, "alice", json={"user_id": 2}).status_code == 200
    assert call(raw_client, "POST", "/rooms/residents/leave", 1, "alice").status_code == 204  # then goes: bob owns it
    room = call(raw_client, "GET", "/rooms/residents", 2, "bob").json()
    assert room["user_id"] == 2 and room["me"]["role"] == "owner"
    assert call(raw_client, "POST", "/rooms/residents/leave", 2, "bob").status_code == 204  # the last one: the room closes, it stays
    closed = call(raw_client, "GET", "/rooms/residents", 2, "bob").json()
    assert closed["state"] == "closed" and closed["members"] == 0 and closed["me"]["status"] == "left"
    assert closed["user_id"] == 2  # a room that closed stays with its last owner
    assert call(raw_client, "GET", "/rooms", 3, "carol").json() == []  # a closed room is not listed


# ---- looking after a room ---------------------------------------------------------------------------------------


def test_only_the_owner_changes_or_deletes_a_room(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "PATCH", "/rooms/residents", 2, "bob", json={"title": "Mine"}).status_code == 403
    assert call(raw_client, "DELETE", "/rooms/residents", 2, "bob").status_code == 403
    changed = call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"title": "Renamed", "category": "talk"})
    assert changed.json()["title"] == "Renamed" and changed.json()["category"] == "talk"
    assert call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"description": "d"}).status_code == 422  # a room has no description
    assert call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"capacity": 3}).status_code == 200
    assert call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"capacity": 1}).status_code == 422
    assert call(raw_client, "DELETE", "/rooms/residents", 1, "alice").status_code == 204
    gone = call(raw_client, "GET", "/rooms/residents", 1, "alice").json()  # hidden for others, kept for its owner
    assert gone["state"] == "deleted"
    assert call(raw_client, "GET", "/rooms/residents", 2, "bob").status_code == 404
    assert call(raw_client, "GET", "/rooms", 2, "bob").json() == []


def test_the_capacity_cannot_go_below_the_members(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={})
    assert call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"capacity": 2}).status_code == 409


def test_a_closed_room_cannot_be_posted_in_and_can_be_opened_again(raw_client):
    make(raw_client)
    with ws(raw_client, "residents") as alice:
        call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"state": "closed"})
        alice.send_json({"content": "hello?"})
        assert frame_of(alice, "error")["error"] == "Room is not open"
        call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"state": "open"})
        alice.send_json({"content": "back"})
        assert next_text(alice)["content"] == "back"
    kinds = [m["content"] for m in call(raw_client, "GET", "/rooms/residents/messages").json() if m["kind"] == "system"]
    assert kinds == ["closed:alice", "reopened:alice"]  # the conversation says what happened to the room


def test_a_ban_closes_the_sockets_and_keeps_the_person_out(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents", 2, "bob") as bob:
        frame_of(bob, "presence")
        banned = call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"status": "banned"})
        assert banned.status_code == 200
        with pytest.raises(WebSocketDisconnect) as info:
            while True:
                bob.receive_json()
        assert info.value.reason == "You are banned from this room"
    assert call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={}).status_code == 403
    assert refused(raw_client, "residents").reason == "You are banned from this room"
    listed = {m["username"]: m["status"] for m in call(raw_client, "GET", "/rooms/residents/members", 3, "carol").json()}
    assert listed == {"alice": "joined", "bob": "banned"}  # the list is of everyone who was in the room, with the status


def test_a_removed_member_may_come_back_but_the_owner_cannot_be_touched(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "DELETE", "/rooms/residents/members/2", 1, "alice").status_code == 204
    assert call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={}).status_code == 200
    assert call(raw_client, "PATCH", "/rooms/residents/members/1", 1, "alice", json={"status": "banned"}).status_code == 403
    assert call(raw_client, "DELETE", "/rooms/residents/members/1", 1, "alice").status_code == 403
    assert call(raw_client, "PATCH", "/rooms/residents/members/9", 1, "alice", json={"status": "banned"}).status_code == 404


def test_only_the_owner_bans_and_nobody_is_a_moderator(raw_client):
    make(raw_client)
    for uid, name in ((2, "bob"), (3, "carol"), (4, "dave")):
        call(raw_client, "POST", "/rooms/residents/join", uid, name, json={})
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"role": "moderator"}).status_code == 422  # there are no moderators
    assert call(raw_client, "PATCH", "/rooms/residents/members/3", 2, "bob", json={"status": "banned"}).status_code == 403  # a member cannot
    assert call(raw_client, "PATCH", "/rooms/residents/members/3", 1, "alice", json={"status": "banned"}).status_code == 200  # the owner can
    assert "attributes" not in call(raw_client, "GET", "/rooms/residents/members", 2, "bob").json()[0]


def test_ownership_can_be_handed_over(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "POST", "/rooms/residents/transfer", 2, "bob", json={"user_id": 2}).status_code == 403
    assert call(raw_client, "POST", "/rooms/residents/transfer", 1, "alice", json={"user_id": 1}).status_code == 422
    room = call(raw_client, "POST", "/rooms/residents/transfer", 1, "alice", json={"user_id": 2}).json()
    assert room["user_id"] == 2 and room["me"]["role"] == "member"  # the answer is for the one who handed it over
    assert call(raw_client, "GET", "/rooms/residents", 2, "bob").json()["me"]["role"] == "owner"


# ---- what is said in a room -------------------------------------------------------------------------------------


def test_only_members_can_open_a_socket(raw_client):
    make(raw_client)
    assert refused(raw_client, "residents").reason == "You are not a member of this room"
    assert refused(raw_client, "nowhere").reason == "Room not found"


def test_a_muted_member_cannot_speak_until_the_owner_lifts_it(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    muted = call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"muted": True})
    assert muted.status_code == 200 and muted.json()["muted"] is True and muted.json()["status"] == "joined"
    with ws(raw_client, "residents", 2, "bob") as bob:
        bob.send_json({"content": "hi"})
        assert frame_of(bob, "error")["error"] == "You are muted"
        assert call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"muted": False}).json()["muted"] is False
        bob.send_json({"content": "hi again"})
        assert next_message(bob)["content"] == "hi again"
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", 2, "bob", json={"muted": False}).status_code == 403  # a member does not lift their own mute


def test_a_message_can_answer_another_and_the_frame_says_who_wrote_it(raw_client):
    make(raw_client)
    with ws(raw_client, "residents") as alice:
        alice.send_json({"content": "question"})
        question = next_message(alice)
        alice.send_json({"content": "answer", "reply_to": question["id"]})
        answer = next_message(alice)
        alice.send_json({"content": "orphan", "reply_to": 9999})
        orphan = next_message(alice)
    assert answer["reply_to_id"] == question["id"] and answer["user_id"] == 1
    assert orphan["reply_to_id"] is None


def test_an_author_or_the_owner_deletes_a_message_and_it_leaves_the_history(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents", 2, "bob") as bob, ws(raw_client, "residents", 1, "alice") as alice:
        bob.send_json({"content": "mine"})
        mine = next_message(bob)
        next_message(alice)
        bob.send_json({"content": "another"})
        other = next_message(bob)
        next_message(alice)
        assert call(raw_client, "DELETE", f"/rooms/residents/messages/{mine['id']}", 2, "bob").status_code == 204
        assert frame_of(alice, "deleted")["id"] == mine["id"]
        call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={})
        assert call(raw_client, "DELETE", f"/rooms/residents/messages/{other['id']}", 3, "carol").status_code == 403
        assert call(raw_client, "DELETE", f"/rooms/residents/messages/{other['id']}", 1, "alice").status_code == 204
    assert texts(raw_client, "residents") == []
    assert call(raw_client, "DELETE", f"/rooms/residents/messages/{mine['id']}", 2, "bob").status_code == 404


def test_any_member_pins_and_unpins_and_someone_outside_the_room_cannot(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents", 1, "alice") as alice:
        alice.send_json({"content": "rules"})
        message = next_message(alice)
        assert call(raw_client, "PUT", f"/rooms/residents/messages/{message['id']}/pin", 3, "carol").status_code in (403, 404)  # not in the room
        assert call(raw_client, "PUT", f"/rooms/residents/messages/{message['id']}/pin", 2, "bob").status_code == 204  # a member, not a moderator
        assert call(raw_client, "PUT", f"/rooms/residents/messages/{message['id']}/pin", 1, "alice").status_code == 204
        assert frame_of(alice, "pinned") == {"type": "pinned", "id": message["id"], "pinned": True}
    assert texts(raw_client, "residents", 2, "bob")[0]["pinned_at"] is not None
    call(raw_client, "DELETE", f"/rooms/residents/messages/{message['id']}/pin", 1, "alice")
    assert texts(raw_client, "residents", 2, "bob")[0]["pinned_at"] is None


def test_history_pages_backwards(raw_client):
    make(raw_client)
    with ws(raw_client, "residents") as alice:
        ids = []
        for text in ("one", "two", "three", "four"):
            alice.send_json({"content": text})
            ids.append(next_message(alice)["id"])
    page = call(raw_client, "GET", f"/rooms/residents/messages?limit=2&before={ids[3]}").json()
    assert [m["content"] for m in page] == ["two", "three"]


def test_a_public_room_can_be_read_before_joining_but_a_ban_shuts_the_door(raw_client):
    make(raw_client)
    assert call(raw_client, "GET", "/rooms/residents/messages", 2, "bob").status_code == 200
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"status": "banned"})
    assert call(raw_client, "GET", "/rooms/residents/messages", 2, "bob").status_code == 403


# ---- direct chats -----------------------------------------------------------------------------------------------


def test_a_direct_chat_is_with_someone_the_chat_knows_and_is_made_once(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "POST", "/dm", 3, "carol", json={"user_id": 99}).status_code == 404  # nobody the chat knows
    assert call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 1}).status_code == 422  # not oneself
    first = call(raw_client, "POST", "/dm", 2, "bob", json={"user_id": 1})
    assert first.status_code == 200
    room = first.json()
    assert room["kind"] == "dm" and room["visibility"] == "private" and room["capacity"] == 2 and room["members"] == 2
    again = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 2}).json()
    assert again["slug"] == room["slug"]
    with ws(raw_client, room["slug"], 2, "bob") as bob:
        bob.send_json({"content": "is it still for sale?"})
        assert next_message(bob)["content"] == "is it still for sale?"
    assert call(raw_client, "GET", f"/rooms/{room['slug']}", 3, "carol").status_code == 404  # private to the two
    assert [r["slug"] for r in call(raw_client, "GET", "/rooms").json()] == ["residents"]  # a direct chat is not in the public list


def test_someone_who_left_a_direct_chat_comes_back_to_it(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    slug = call(raw_client, "POST", "/dm", 2, "bob", json={"user_id": 1}).json()["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/leave", 2, "bob")
    back = call(raw_client, "POST", "/dm", 2, "bob", json={"user_id": 1}).json()
    assert back["slug"] == slug and back["me"]["status"] == "joined"


# ---- the people ------------------------------------------------------------------------------------------------


def two_rooms(raw_client):
    """alice, bob and carol in one room, dave in another."""
    make(raw_client, title="Talk")
    for uid, name in ((2, "bob"), (3, "carol")):
        call(raw_client, "POST", "/rooms/talk/join", uid, name, json={})
    make(raw_client, uid=4, name="dave", title="Elsewhere")


def test_there_is_no_room_everyone_is_in(raw_client):
    assert call(raw_client, "GET", "/rooms?scope=mine", 1, "alice").json() == []
    assert call(raw_client, "GET", "/rooms/public", 1, "alice").status_code == 404
    assert call(raw_client, "GET", "/rooms", 1, "alice").json() == []


def test_anyone_the_chat_knows_can_be_written_to_privately(raw_client):
    two_rooms(raw_client)
    dm = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 2})  # bob shares a room with alice: at once
    assert dm.status_code == 200 and dm.json()["kind"] == "dm" and dm.json()["members"] == 2
    asked = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 4})  # dave is in a room alice is not: a request
    assert asked.status_code == 200 and asked.json()["kind"] == "dm" and asked.json()["members"] == 1
    assert call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 99}).status_code == 404


def test_the_lobby_says_how_many_are_online_and_moves_when_people_come_or_go(raw_client):
    with raw_client.websocket_connect("/ws-lobby", headers=ws_headers(1, "alice")) as watcher:
        first = watcher.receive_json()
        assert first["online"] == 1 and "people" in first
        with raw_client.websocket_connect("/ws-lobby", headers=ws_headers(2, "bob")):
            frame = watcher.receive_json()
            assert frame["online"] == 2 and frame["people"] > first["people"]


# ---- searching the rooms ---------------------------------------------------------------------------------------


def found(client, query, scope="public", uid=9, name="zed"):
    response = call(client, "GET", f"/rooms?scope={scope}&q={query}", uid, name)
    assert response.status_code == 200, response.text
    return {room["slug"]: room for room in response.json()}


def test_a_search_looks_in_every_field_of_a_room_at_once(raw_client):
    make(raw_client, title="Garage sale", slug="sale-q7", category="neighbours")
    make(raw_client, title="Quiet", slug="quiet")
    assert set(found(raw_client, "garage")) == {"sale-q7"}  # the title
    assert set(found(raw_client, "SALE-Q")) == {"sale-q7"}  # the address, whatever the case
    assert set(found(raw_client, "neighbours")) == {"sale-q7"}  # the group label
    assert found(raw_client, "zzz") == {}


def test_a_search_also_finds_a_room_by_the_name_of_a_member(raw_client):
    make(raw_client, title="Club")
    call(raw_client, "POST", "/rooms/club/join", 2, "barbara", json={})
    make(raw_client, title="Other")
    result = found(raw_client, "barb")
    assert set(result) == {"club"} and result["club"]["hit"]["members"] == ["barbara"]
    assert result["club"]["hit"]["fields"] == []


def test_a_search_also_finds_a_room_by_what_was_said_in_it(raw_client):
    make(raw_client, title="Talk")
    make(raw_client, title="Silent")
    with ws(raw_client, "talk") as alice:
        alice.send_json({"content": "Anyone selling a second-hand bicycle near the market?"})
        said = next_message(alice)
        alice.send_json({"content": "a bicycle to give away"})
        later = next_message(alice)
    result = found(raw_client, "BICYCLE")
    assert set(result) == {"talk"}
    hit = result["talk"]["hit"]["message"]
    assert hit["id"] == later["id"] and hit["username"] == "alice" and "bicycle" in hit["content"].lower()  # the latest
    call(raw_client, "DELETE", f"/rooms/talk/messages/{later['id']}", 1, "alice")
    call(raw_client, "DELETE", f"/rooms/talk/messages/{said['id']}", 1, "alice")
    assert found(raw_client, "bicycle") == {}  # a deleted message is not searched


def test_a_long_message_is_cut_to_the_words(raw_client):
    make(raw_client, title="Talk")
    with ws(raw_client, "talk") as alice:
        alice.send_json({"content": "x" * 300 + " needle " + "y" * 300})
        next_message(alice)
    snippet = found(raw_client, "needle")["talk"]["hit"]["message"]["content"]
    assert "needle" in snippet and len(snippet) <= 125 and snippet.startswith("…") and snippet.endswith("…")


def test_the_words_of_a_search_are_literal(raw_client):
    make(raw_client, title="100% fun")
    make(raw_client, title="Plain")
    assert set(found(raw_client, "100%25")) == {"100-fun"}
    assert found(raw_client, "%25") != {} and set(found(raw_client, "%25")) == {"100-fun"}  # a % is a % and not "anything"
    assert found(raw_client, "_") == {}


def test_a_search_does_not_open_a_private_room_through_its_members_or_messages(raw_client):
    make(raw_client, title="Secret", visibility="private", join_policy="approval")
    bring(raw_client, "secret", 2, "bobby")
    with ws(raw_client, "secret") as alice:
        alice.send_json({"content": "the password is swordfish"})
        next_message(alice)
    for words in ("bobby", "swordfish", "secret"):
        assert found(raw_client, words) == {}  # not to someone outside
    mine = found(raw_client, "swordfish", scope="mine", uid=1, name="alice")
    assert set(mine) == {"secret"} and mine["secret"]["hit"]["message"]["content"] == "the password is swordfish"
    assert found(raw_client, "swordfish", scope="mine", uid=9, name="zed") == {}


def test_a_search_without_words_has_no_hits(raw_client):
    make(raw_client, title="Talk")
    plain = found(raw_client, "")
    assert plain["talk"]["hit"] is None
