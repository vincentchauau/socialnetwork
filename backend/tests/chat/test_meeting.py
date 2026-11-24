"""The video call of a room lives in the chat: members start and join it with a LiveKit ticket, the owner or the starter ends it, a removed person
cannot follow it."""

import base64
import hashlib
import hmac
import json

import pytest

from api.chat import livekit_tickets
from tests.chat.test_room_api import call

KEY, SECRET = "lkdevtest", "a" * 40


@pytest.fixture(autouse=True)
def livekit(monkeypatch):
    monkeypatch.setenv("LIVEKIT_API_KEY", KEY)
    monkeypatch.setenv("LIVEKIT_API_SECRET", SECRET)
    monkeypatch.setenv("LIVEKIT_URL", "ws://lk.test:7880")
    closed = []
    monkeypatch.setattr(livekit_tickets, "close_room", lambda room: closed.append(room) or True)
    return closed


def claims_of(token: str) -> dict:
    head, body, signature = token.split(".")
    expected = base64.urlsafe_b64encode(hmac.new(SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    assert signature == expected  # signed with the secret
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def make_room(client):
    call(client, "POST", "/rooms", 1, "alice", json={"slug": "talk", "title": "Talk", "visibility": "public"})
    call(client, "POST", "/rooms/talk/join", 2, "bob", json={})


def start(client, uid=1, name="alice"):
    return call(client, "POST", "/rooms/talk/meeting/start", uid, name)


def test_a_member_starts_the_meeting_and_the_others_join_the_same_one_each_with_their_own_ticket(raw_client):
    make_room(raw_client)
    assert call(raw_client, "GET", "/rooms/talk/meeting", 2, "bob").status_code == 404  # none yet
    first = start(raw_client)
    assert first.status_code == 200 and first.json()["server"] == "ws://lk.test:7880" and first.json()["name"].startswith("sn-")
    second = start(raw_client, 2, "bob").json()
    assert second["id"] == first.json()["id"] and second["name"] == first.json()["name"]
    mine, theirs = claims_of(first.json()["token"]), claims_of(second["token"])
    assert mine["iss"] == KEY and mine["sub"] == "1" and mine["name"] == "alice"
    assert theirs["sub"] == "2" and theirs["name"] == "bob"
    assert mine["video"] == {"room": first.json()["name"], "roomJoin": True, "canPublish": True, "canSubscribe": True}
    assert mine["exp"] - mine["nbf"] <= livekit_tickets.TICKET_SECONDS + 10
    assert call(raw_client, "GET", "/rooms/talk/meeting", 2, "bob").json()["name"] == first.json()["name"]


def test_without_a_key_for_livekit_there_are_no_calls(raw_client, monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY")
    make_room(raw_client)
    assert start(raw_client).status_code == 503


def test_only_members_of_an_open_room_start_it(raw_client):
    make_room(raw_client)
    assert start(raw_client, 3, "carol").status_code in (403, 404)  # not in the room
    call(raw_client, "PATCH", "/rooms/talk", 1, "alice", json={"state": "closed"})
    assert start(raw_client).status_code == 409


def test_the_starter_or_the_owner_ends_it_and_another_member_cannot(raw_client, livekit):
    make_room(raw_client)
    name = start(raw_client, 2, "bob").json()["name"]
    assert call(raw_client, "POST", "/rooms/talk/meeting/end", 1, "alice").status_code == 204  # the owner
    assert call(raw_client, "GET", "/rooms/talk/meeting", 1, "alice").status_code == 404
    start(raw_client, 1, "alice")
    assert call(raw_client, "POST", "/rooms/talk/meeting/end", 2, "bob").status_code == 403  # neither the starter nor the owner
    assert call(raw_client, "POST", "/rooms/talk/meeting/end", 1, "alice").status_code == 204
    import time

    deadline = time.time() + 3
    while name not in livekit and time.time() < deadline:
        time.sleep(0.05)
    assert name in livekit  # the room is closed at LiveKit too, so nobody stays in it


def test_sending_a_person_away_ends_the_meeting_so_the_next_one_has_a_new_name(raw_client, livekit):
    make_room(raw_client)
    old = start(raw_client).json()["name"]
    assert call(raw_client, "DELETE", "/rooms/talk/members/2", 1, "alice").status_code == 204
    assert call(raw_client, "GET", "/rooms/talk/meeting", 1, "alice").status_code == 404
    assert start(raw_client).json()["name"] != old


def test_ending_closes_every_open_meeting_of_the_room(raw_client):
    from sqlalchemy import select

    from api.chat.models import Meeting

    make_room(raw_client)
    start(raw_client)
    with raw_client.app.state.session_factory() as db:  # an older one that was left open (made by two starts at once before)
        room_id = db.scalar(select(Meeting.room_id))
        db.add(Meeting(room_id=room_id, room_name="sn-old", started_by=1))
        db.commit()
    assert call(raw_client, "POST", "/rooms/talk/meeting/end", 1, "alice").status_code == 204
    assert call(raw_client, "GET", "/rooms/talk/meeting", 1, "alice").status_code == 404
