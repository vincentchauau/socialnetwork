"""A stranger asks to write to someone: the request, the answer, and the inbox that shows what waits."""

from tests.chat.social.people import join, make_people
from tests.chat.test_room_api import call, make, next_text, ws


def ask(client, uid=1, name="alice", other=2):
    response = call(client, "POST", "/dm", uid, name, json={"user_id": other})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_one_asked_reads_what_was_written_and_the_request_waits_under_requests_not_mine(raw_client):
    make_people(raw_client)
    room = ask(raw_client)
    with ws(raw_client, room["slug"], 1, "alice") as alice:
        alice.send_json({"content": "hi, we met at the market"})
        next_text(alice)
    read = call(raw_client, "GET", f"/rooms/{room['slug']}/messages", 2, "bob")
    assert read.status_code == 200 and [m["content"] for m in read.json() if m["kind"] == "text"] == ["hi, we met at the market"]
    assert [r["slug"] for r in call(raw_client, "GET", "/rooms", 2, "bob", params={"scope": "requests"}).json()] == [room["slug"]]
    assert call(raw_client, "GET", "/rooms", 2, "bob", params={"scope": "mine"}).json() == []
    assert call(raw_client, "GET", "/rooms", 3, "carol", params={"scope": "requests"}).json() == []  # not carol's
    assert call(raw_client, "GET", f"/rooms/{room['slug']}/messages", 3, "carol").status_code == 404


def test_a_stranger_may_send_three_messages_before_an_answer(raw_client):
    make_people(raw_client)
    room = ask(raw_client)
    with ws(raw_client, room["slug"], 1, "alice") as alice:
        for n in range(3):
            alice.send_json({"content": f"message {n}"})
            next_text(alice)
        alice.send_json({"content": "and a fourth"})
        error = alice.receive_json()
        assert error["type"] == "error" and error["error"] == "Waiting for approval"


def test_only_the_one_asked_answers_and_a_block_stops_the_request(raw_client):
    make_people(raw_client)
    room = ask(raw_client)
    assert call(raw_client, "POST", f"/rooms/{room['slug']}/accept", 1, "alice").status_code == 404  # the asker has nothing to accept
    assert call(raw_client, "POST", f"/rooms/{room['slug']}/decline", 3, "carol").status_code == 404
    call(raw_client, "POST", "/blocks/1", 2, "bob")  # bob blocks alice before answering
    assert call(raw_client, "POST", f"/rooms/{room['slug']}/accept", 2, "bob").status_code == 403
    assert call(raw_client, "POST", "/dm", 3, "carol", json={"user_id": 2}).status_code == 200  # carol is not blocked
    call(raw_client, "POST", "/blocks/3", 2, "bob")
    assert call(raw_client, "POST", "/dm", 3, "carol", json={"user_id": 2}).status_code == 403


def test_people_who_share_a_room_write_at_once_and_requests_waiting_are_limited(raw_client, monkeypatch):
    from api.chat import service

    make(raw_client, title="Market")
    call(raw_client, "POST", "/rooms/market/join", 2, "bob", json={})
    assert ask(raw_client)["me"]["status"] == "joined" and call(raw_client, "GET", "/rooms/dm-1-2", 2, "bob").json()["me"]["status"] == "joined"
    monkeypatch.setattr(service, "MAX_DM_REQUESTS_WAITING", 2)
    for uid, name in ((3, "carol"), (4, "dave"), (5, "erin")):
        join(raw_client, uid, name)
    assert call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 3}).status_code == 200  # a stranger: a request that waits
    assert call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 4}).status_code == 200
    assert call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 5}).status_code == 429  # two requests are waiting already (the chat with bob is not one)


def test_the_inbox_has_the_newest_conversation_first_with_what_was_said_last(raw_client):
    make(raw_client, title="Old room")
    make(raw_client, title="New room")
    with ws(raw_client, "old-room") as old:
        old.send_json({"content": "first words"})
        next_text(old)
    with ws(raw_client, "new-room") as new:
        new.send_json({"content": "a   line   with\nspaces and a very long tail " + "x" * 120})
        next_text(new)
    mine = call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "mine"}).json()
    assert [r["slug"] for r in mine] == ["new-room", "old-room"]
    last = mine[0]["last_message"]
    assert last["username"] == "alice" and last["content"].startswith("a line with spaces and a very long tail") and last["content"].endswith("…")
    assert len(last["content"]) <= 81
    with ws(raw_client, "old-room") as old:
        old.send_json({"content": "now this one is newest"})
        next_text(old)
    assert [r["slug"] for r in call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "mine"}).json()] == ["old-room", "new-room"]
    assert "last_message" in call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "public"}).json()[0]
    assert call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "public"}).json()[0]["last_message"] is None  # (not worked out for the public list)
