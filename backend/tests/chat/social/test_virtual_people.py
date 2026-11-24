"""The virtual people of the pool (rows of `users`): they are found and labelled, and are friends as soon as they are asked."""

from datetime import date

from sn_shared.directory import Person
from sn_shared.testing import add_person

from api.chat.social.events import on_user_deleted
from tests.chat.social.people import join
from tests.chat.test_room_api import call


def arrive(client, user_id=500, name="Lan_Nguyen", kind="virtual", display_name=None, **profile):
    """A virtual person of the pool: a row of `users` (center makes them there); `display_name` is the `name` of the profile."""
    add_person(client.app.state.session_factory, user_id, name, kind=kind, name=display_name, **profile)


def test_a_virtual_person_who_was_blocked_cannot_be_asked_to_be_a_friend(raw_client):
    join(raw_client, 1, "alice")
    arrive(raw_client)
    assert call(raw_client, "POST", "/blocks/500", 1, "alice").status_code == 204
    assert call(raw_client, "POST", "/friends/500", 1, "alice").status_code == 403


# ---- companions: drawn at random from the pool ---------------------------------------------------------------------


def pool(client, size=12):
    regions = ("Hà Nội", "Đà Lạt")
    for number in range(size):
        arrive(
            client, 500 + number, f"Virt_{number}", region=regions[number % 2], interests=["đọc sách", "cà phê"] if number % 3 == 0 else ["yoga"],
            birth_date=date(1990, 1, 1), headline="Bạn trò chuyện", display_name=f"Virt {number}",
        )


def draw(client, uid=1, name="alice", **body):
    return call(client, "POST", "/companions/draw", uid, name, json=body)


def test_a_virtual_person_is_written_to_like_any_other_and_the_chat_opens_at_once(raw_client):
    pool(raw_client, 1)
    join(raw_client, 1, "alice")
    room = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 500})
    assert room.status_code == 200
    from api.chat.models import RoomMember

    with raw_client.app.state.session_factory() as db:
        assert {m.user_id: m.status for m in db.query(RoomMember)} == {1: "joined", 500: "joined"}


def test_deleting_the_owner_ends_their_companionships(raw_client):
    pool(raw_client, 1)
    draw(raw_client, count=1)
    with raw_client.app.state.session_factory() as db:
        on_user_deleted(db, 1)
        db.commit()
    with raw_client.app.state.session_factory() as db:
        from api.chat.social.models import COMPANION, Edge

        assert db.query(Edge).filter(Edge.kind == COMPANION).count() == 0


# ---- "add N virtual people" to a room, and the seats of the Werewolf named after them -----------------------------------


def room_members(client, slug, uid=1, name="alice"):
    return {m["username"] for m in call(client, "GET", f"/rooms/{slug}/members", uid, name).json() if m["status"] == "joined"}


def test_adding_stops_at_the_limit_of_the_room_and_says_so(raw_client, monkeypatch):
    from api.chat import virtual_reply
    from tests.chat.test_room_api import make

    MAX_VIRTUAL_PER_ROOM = 8  # the limit is a setting: a small one keeps this test short
    monkeypatch.setattr(virtual_reply, "MAX_VIRTUAL_PER_ROOM", MAX_VIRTUAL_PER_ROOM)
    pool(raw_client, 14)
    slug = make(raw_client)["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 5})
    second = call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 5}).json()
    assert len(second["added"]) == MAX_VIRTUAL_PER_ROOM - 5 and second["why"]
    third = call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 1}).json()
    assert third["added"] == [] and third["why"]


def test_only_a_member_adds_virtual_people_and_the_count_is_checked(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client)
    slug = make(raw_client)["slug"]
    assert call(raw_client, "POST", f"/rooms/{slug}/virtual", 2, "bob", json={"count": 1}).status_code in (403, 404)
    for count in (0, 201, -1):
        assert call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": count}).status_code == 422
    assert call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice").status_code == 422


def test_the_game_of_a_room_names_its_machine_seats_after_the_virtual_people_in_it(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client)
    slug = make(raw_client)["slug"]
    added = call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 3}).json()["added"]
    made = call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice")
    assert made.status_code == 200, made.text
    game = call(raw_client, "GET", f"/werewolf/rooms/{made.json()['code']}", 1, "alice").json()["state"]
    names = {m["name"] for m in game["members"]}
    assert {a["display_name"] for a in added} <= names
    assert len(game["members"]) == 5 and sum(1 for m in game["members"] if m["isBot"]) == 4


def test_a_game_that_only_follows_the_room_does_not_fill_the_seats_with_virtual_people_again(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client)
    slug = make(raw_client)["slug"]
    assert call(raw_client, "POST", f"/rooms/{slug}/game?follow=1", 1, "alice").status_code == 200
    count = lambda: len(call(raw_client, "GET", f"/rooms/{slug}/members", 1, "alice").json())  # noqa: E731
    assert count() == 1  # (a game that follows adds nobody: the first time, asked for, does)
    assert call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice").status_code == 200
    assert count() == 5


def test_a_virtual_person_in_a_room_is_listed_as_there_and_as_virtual(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client)
    slug = make(raw_client)["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 2})
    rows = {m["username"]: m for m in call(raw_client, "GET", f"/rooms/{slug}/members", 1, "alice").json()}
    virtual = [m for m in rows.values() if m["virtual"]]
    assert len(virtual) == 2 and all(m["online"] and m["status"] == "joined" for m in virtual)
    assert rows["alice"]["virtual"] is False and rows["alice"]["online"] is False  # (nobody has the room open in this test)


def test_the_game_of_a_room_follows_the_room_when_virtual_people_come_after_it_was_made(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client, 14)
    slug = make(raw_client)["slug"]
    code = call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice").json()["code"]

    def seats():
        return call(raw_client, "GET", f"/werewolf/rooms/{code}", 1, "alice").json()["state"]["members"]

    def room_names():
        return {m["display_name"] for m in call(raw_client, "GET", f"/people", 1, "alice", params={"q": "virt"}).json() if m["virtual"]}

    assert len(seats()) == 5 and all(m["origin"] == "virtual" for m in seats() if m["isBot"])  # the room had alice: four virtual people came in to make five
    more = call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 3}).json()["added"]
    call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice")
    grown = seats()
    assert len(grown) == 8 and {a["display_name"] for a in more} <= {m["name"] for m in grown}
    members = {m["username"] for m in call(raw_client, "GET", f"/rooms/{slug}/members", 1, "alice").json() if m["status"] == "joined"}
    assert len(members) == 8  # the seats are the people of the room, nobody else


def test_the_seats_of_the_game_are_the_people_of_the_room_and_nobody_else(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client, 10)
    slug = make(raw_client)["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/join", 2, "bob", json={})
    call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 2})
    code = call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice").json()["code"]

    def seats():
        return call(raw_client, "GET", f"/werewolf/rooms/{code}", 1, "alice").json()["state"]["members"]

    names = {m["name"] for m in seats()}
    assert len(seats()) == 5 and "bob" in names  # bob has a seat of his name before he sits in the game
    assert sum(1 for m in seats() if not m["isBot"]) == 1
    call(raw_client, "POST", f"/rooms/{slug}/game", 2, "bob")  # he sits in it: his seat, not another
    assert [m["name"] for m in seats() if not m["isBot"]] == ["alice", "bob"] and len(seats()) == 5
    # more bots than the room needs (the host added some) are taken away at the next look; the room's own people stay
    call(raw_client, "POST", f"/werewolf/rooms/{code}/bots", 1, "alice", json={"count": 3})
    assert len(seats()) == 8
    call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice")
    assert len(seats()) == 5 and {m["name"] for m in seats()} >= names - {"alice", "bob"} | {"alice", "bob"}


def test_each_seat_says_who_it_is_for_so_the_lobby_counts_what_the_room_has(raw_client):
    from tests.chat.test_room_api import make

    pool(raw_client, 10)
    slug = make(raw_client)["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/join", 2, "bob", json={})
    added = call(raw_client, "POST", f"/rooms/{slug}/virtual", 1, "alice", json={"count": 1}).json()["added"]
    code = call(raw_client, "POST", f"/rooms/{slug}/game", 1, "alice").json()["code"]
    members = call(raw_client, "GET", f"/werewolf/rooms/{code}", 1, "alice").json()["state"]["members"]
    origin = {m["name"]: m["origin"] for m in members}
    assert origin["alice"] == "" and origin["bob"] == "human" and origin[added[0]["display_name"]] == "virtual"
    assert sorted(origin.values()) == ["", "human", "virtual", "virtual", "virtual"]  # alice, bob, and three virtual people (the machine's players are virtual people)
    call(raw_client, "POST", f"/rooms/{slug}/game", 2, "bob")  # bob sits: his seat is a person's now
    members = call(raw_client, "GET", f"/werewolf/rooms/{code}", 1, "alice").json()["state"]["members"]
    assert [m["origin"] for m in members if m["name"] == "bob"] == [""] and not [m for m in members if m["name"] == "bob"][0]["isBot"]
