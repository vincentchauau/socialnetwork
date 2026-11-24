"""What the chat asks of the game with a signed call: the game of a room is made and joined, and goes with the room."""

import json

import pytest

from sn_shared import servicesig

SECRET = "s" * 32


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("WEREWOLF_SECRET", SECRET)


def post(client, payload, secret=SECRET, path="/internal/ensure"):
    body = json.dumps(payload).encode()
    return client.post(path, content=body, headers=servicesig.sign(secret, body, f"POST {path}") if secret else {})


def ensure_body(**changes):
    return {"code": "ROOM1", "title": "Residents", "seats": 6, "user_id": 1, "username": "alice", "bot_names": [], **changes}


def test_an_unsigned_or_badly_signed_call_is_refused(client):
    assert post(client, ensure_body(), secret=None).status_code == 401
    assert post(client, ensure_body(), secret="x" * 32).status_code == 401
    assert client.delete("/internal/rooms/ROOM1").status_code == 401
    assert client.app.state.ww_store.get("ROOM1") is None


def test_without_a_secret_set_nothing_is_trusted(client, monkeypatch):
    monkeypatch.setenv("WEREWOLF_SECRET", "")
    assert post(client, ensure_body(), secret=SECRET).status_code == 401


def test_the_game_of_a_room_is_made_with_its_seats_and_joined_by_the_others(client):
    assert post(client, ensure_body(bot_names=[["Lan_Nguyen", "Lan Nguyen"]])).json() == {"ok": True}
    room = client.app.state.ww_store.get("ROOM1")
    assert room is not None and room.seat_index(1) is not None
    assert post(client, ensure_body(user_id=2, username="bob")).status_code == 200
    assert client.app.state.ww_store.get("ROOM1").seat_index(2) is not None
    assert post(client, ensure_body(user_id=2, username="bob")).status_code == 200  # sitting again changes nothing


def test_the_reasons_the_game_gives_are_told_with_their_status(client):
    client.app.state.ww_store.max_rooms_per_user = 1
    assert post(client, ensure_body()).status_code == 200
    refused = post(client, ensure_body(code="ROOM2"))
    assert refused.status_code == 409 and refused.json()["detail"] == "You are in too many games"


def test_a_body_that_is_not_one_is_refused_after_the_signature(client):
    for payload in ({}, ensure_body(seats=0), ensure_body(username=""), ensure_body(extra=1), [1]):
        assert post(client, payload).status_code == 422, payload
    body = b"not json"
    assert client.post("/internal/ensure", content=body, headers=servicesig.sign(SECRET, body, "POST /internal/ensure")).status_code == 422


def test_the_game_goes_with_its_room(client):
    post(client, ensure_body())
    assert client.app.state.ww_store.get("ROOM1") is not None
    gone = client.delete("/internal/rooms/ROOM1", headers=servicesig.sign(SECRET, b"", "DELETE /internal/rooms/ROOM1"))
    assert gone.status_code == 204 and client.app.state.ww_store.get("ROOM1") is None
    assert client.delete("/internal/rooms/ROOM1", headers=servicesig.sign(SECRET, b"", "DELETE /internal/rooms/ROOM1")).status_code == 204  # nothing to drop is not an error
