"""A room is open to anyone or joined with approval; either way it has an owner, who decides: close, reopen, status, who comes in, who stays."""

from tests.chat.test_room_api import call, make


def role_of(client, slug, uid, as_uid=1, as_name="alice"):
    return call(client, "GET", f"/rooms/{slug}/members/{uid}", as_uid, as_name).json()["role"]


def test_the_maker_of_an_open_room_owns_it(raw_client):
    room = make(raw_client, join_policy="open")
    assert room["me"]["role"] == "owner" and room["owner_name"] == "alice"
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert role_of(raw_client, "residents", 1) == "owner"
    assert role_of(raw_client, "residents", 2) == "member"


def test_the_owner_of_an_open_room_kicks_bans_and_changes_it_and_a_member_cannot(raw_client):
    make(raw_client, join_policy="open")
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "PATCH", "/rooms/residents", 2, "bob", json={"title": "Mine"}).status_code == 403
    assert call(raw_client, "PATCH", "/rooms/residents/members/1", 2, "bob", json={"status": "banned"}).status_code == 403
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", json={"status": "banned"}).status_code == 200
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", json={"status": "joined"}).status_code == 200  # lifted
    assert call(raw_client, "DELETE", "/rooms/residents/members/2").status_code == 204  # kicked
    assert call(raw_client, "PATCH", "/rooms/residents", json={"title": "Mine"}).status_code == 200


def test_an_open_room_takes_anyone_and_a_room_with_approval_makes_them_wait(raw_client):
    make(raw_client, title="Open", join_policy="open")
    make(raw_client, title="Closed", join_policy="approval")
    assert call(raw_client, "POST", "/rooms/open/join", 2, "bob", json={}).json()["me"]["status"] == "joined"
    assert call(raw_client, "POST", "/rooms/closed/join", 2, "bob", json={}).json()["me"]["status"] == "pending"


def test_the_owner_of_a_room_with_approval_lets_in_kicks_and_names_himself_in_the_list(raw_client):
    room = make(raw_client, join_policy="approval")
    assert room["me"]["role"] == "owner" and room["owner_name"] == "alice"
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", json={"status": "joined"}).status_code == 200
    assert call(raw_client, "DELETE", "/rooms/residents/members/2").status_code == 204
    listed = {r["slug"]: r for r in call(raw_client, "GET", "/rooms", params={"scope": "mine"}).json()}
    assert listed["residents"]["owner_name"] == "alice"


def test_a_room_cannot_be_made_or_changed_to_be_joined_by_invitation(raw_client):
    assert call(raw_client, "POST", "/rooms", json={"title": "x", "join_policy": "invite"}).status_code == 422
    make(raw_client, join_policy="approval")
    assert call(raw_client, "PATCH", "/rooms/residents", json={"join_policy": "invite"}).status_code == 422


def test_changing_the_status_keeps_the_owner_and_opening_a_room_lets_in_those_who_waited(raw_client):
    make(raw_client, join_policy="approval")
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "PATCH", "/rooms/residents", json={"join_policy": "open"}).status_code == 200
    assert role_of(raw_client, "residents", 1) == "owner"
    assert role_of(raw_client, "residents", 2) == "member"
    members = call(raw_client, "GET", "/rooms/residents/members").json()
    assert {m["username"]: m["status"] for m in members}["bob"] == "joined"
    assert call(raw_client, "PATCH", "/rooms/residents", json={"join_policy": "approval"}).status_code == 200  # still the owner's to change


def test_an_owner_hands_the_room_over_before_leaving_and_the_last_one_to_leave_closes_it(raw_client):
    make(raw_client, join_policy="open")
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "POST", "/rooms/residents/leave").status_code == 409  # someone else is in: choose who comes next
    assert call(raw_client, "POST", "/rooms/residents/transfer", json={"user_id": 2}).status_code == 200
    assert call(raw_client, "POST", "/rooms/residents/leave").status_code == 204
    assert role_of(raw_client, "residents", 2, 2, "bob") == "owner"
    assert call(raw_client, "POST", "/rooms/residents/leave", 2, "bob").status_code == 204
    assert call(raw_client, "GET", "/rooms/residents", 2, "bob").json()["state"] == "closed"


def test_any_member_invites_by_name_into_an_open_room_and_asks_the_owner_in_a_room_with_approval(raw_client):
    make(raw_client, title="Open", join_policy="open")
    make(raw_client, title="Closed", join_policy="approval")
    call(raw_client, "POST", "/rooms/open/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/closed/join", 2, "bob", json={})
    call(raw_client, "PATCH", "/rooms/closed/members/2", json={"status": "joined"})
    call(raw_client, "POST", "/rooms", 3, "carol", json={"title": "Elsewhere", "join_policy": "open"})  # carol is a person the chat knows
    assert call(raw_client, "POST", "/rooms/open/members", 2, "bob", json={"username": "carol"}).status_code == 201
    assert role_of(raw_client, "open", 3) == "member"
    invited = call(raw_client, "POST", "/rooms/closed/members", 2, "bob", json={"username": "carol"})
    assert invited.status_code == 201 and invited.json()["status"] == "pending"  # the owner lets her in
    assert call(raw_client, "PATCH", "/rooms/closed/members/3", json={"status": "joined"}).status_code == 200
    assert call(raw_client, "POST", "/rooms/closed/members", 4, "dave", json={"username": "carol"}).status_code in (403, 404)  # not a member


def test_a_member_cannot_bring_back_someone_the_owner_sent_away(raw_client):
    make(raw_client, join_policy="open")
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={})
    assert call(raw_client, "DELETE", "/rooms/residents/members/3").status_code == 204
    assert call(raw_client, "POST", "/rooms/residents/members", 2, "bob", json={"username": "carol"}).status_code == 403
    assert call(raw_client, "POST", "/rooms/residents/members", 1, "alice", json={"username": "carol"}).status_code == 201  # the owner may


def test_a_chat_of_two_is_named_after_the_other_person_for_each_of_them(raw_client):
    call(raw_client, "POST", "/rooms", 2, "bob", json={"title": "x", "join_policy": "open"})  # bob is known to the chat
    slug = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 2}).json()["slug"]
    assert call(raw_client, "GET", f"/rooms/{slug}", 1, "alice").json()["title"] == "bob"
    assert call(raw_client, "GET", f"/rooms/{slug}", 2, "bob").json()["title"] == "alice"
    mine = [r for r in call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "mine"}).json() if r["kind"] == "dm"]
    assert [r["title"] for r in mine] == ["bob"]


def test_a_room_nobody_owns_goes_to_the_next_person_who_comes_in(raw_client):
    from api.chat.models import Room

    make(raw_client, join_policy="open")
    with raw_client.app.state.session_factory() as session:
        session.query(Room).update({Room.user_id: 99})  # as an old room was: its owner is not in it (nobody who is there owns it)
        session.commit()
    assert call(raw_client, "PATCH", "/rooms/residents", json={"title": "Mine"}).status_code == 403
    joined = call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert joined.status_code == 200 and joined.json()["me"]["role"] == "owner" and joined.json()["owner_name"] == "bob"
    assert call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={}).json()["me"]["role"] == "member"  # the room has its owner now


def test_a_room_has_a_picture_its_owner_sets_and_only_an_address_is_taken(raw_client):
    made = call(raw_client, "POST", "/rooms", json={"title": "Club", "avatar": "https://img.example/club.png"})
    assert made.status_code == 201 and made.json()["avatar"] == "https://img.example/club.png"
    assert call(raw_client, "POST", "/rooms", json={"title": "Bad", "avatar": "javascript:alert(1)"}).status_code == 422
    assert call(raw_client, "PATCH", "/rooms/club", 1, "alice", json={"avatar": "/media/club.png"}).json()["avatar"] == "/media/club.png"
    assert call(raw_client, "PATCH", "/rooms/club", 1, "alice", json={"avatar": ""}).json()["avatar"] == ""
    call(raw_client, "POST", "/rooms/club/join", 2, "bob", json={})
    assert call(raw_client, "PATCH", "/rooms/club", 2, "bob", json={"avatar": "/x.png"}).status_code == 403  # only its owner


def test_the_people_of_a_room_come_with_their_name_and_picture_as_their_profile_lets_the_viewer_see(raw_client):
    from sn_shared.testing import add_person

    make(raw_client, join_policy="open")
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={})
    factory = raw_client.app.state.session_factory
    add_person(factory, 2, "bob", name="Bob Tran", avatar_url="https://img.example/bob.png", visibility={"name": "public", "avatar": "public"})
    add_person(factory, 3, "carol", name="Carol Le", avatar_url="https://img.example/carol.png")  # nothing public: not shown to others
    people = {m["username"]: m for m in call(raw_client, "GET", "/rooms/residents/members", 1, "alice").json()}
    assert (people["bob"]["name"], people["bob"]["avatar"]) == ("Bob Tran", "https://img.example/bob.png")
    assert (people["carol"]["name"], people["carol"]["avatar"]) == ("", "")


def test_a_chat_of_two_has_the_picture_of_the_other_person(raw_client):
    from sn_shared.testing import add_person

    call(raw_client, "GET", "/rooms", 2, "bob")
    add_person(raw_client.app.state.session_factory, 2, "bob", avatar_url="https://img.example/bob.png", visibility={"avatar": "public"})
    slug = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 2}).json()["slug"]
    assert call(raw_client, "GET", f"/rooms/{slug}", 1, "alice").json()["avatar"] == "https://img.example/bob.png"
    assert call(raw_client, "GET", f"/rooms/{slug}", 2, "bob").json()["avatar"] == ""  # alice has none
