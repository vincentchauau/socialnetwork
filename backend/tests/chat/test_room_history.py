"""Nothing is removed: a member or a room only changes status."""

from tests.chat.test_room_api import bring, call, make, next_message, next_text, refused, texts, ws


def test_leaving_and_coming_back_keeps_the_same_membership_and_what_was_said(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents", 2, "bob") as bob:
        bob.send_json({"content": "before"})
        next_text(bob)
    call(raw_client, "POST", "/rooms/residents/leave", 2, "bob")
    away = [m for m in call(raw_client, "GET", "/rooms/residents/members", 1, "alice").json() if m["user_id"] == 2][0]
    assert away["status"] == "left"
    assert [m["content"] for m in texts(raw_client, "residents", 2, "bob")] == ["before"]  # still readable
    assert call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "mine"}).json()[0]["members"] == 1
    past = call(raw_client, "GET", "/rooms", 2, "bob", params={"scope": "past"}).json()
    assert [r["slug"] for r in past] == ["residents"] and past[0]["me"]["status"] == "left"
    assert refused(raw_client, "residents").reason == "You are not a member of this room"  # reads, but does not write
    back = call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert back.json()["me"]["status"] == "joined" and back.json()["members"] == 2
    assert call(raw_client, "GET", "/rooms", 2, "bob", params={"scope": "past"}).json() == []


def test_someone_sent_away_reads_the_old_messages_of_a_private_room_but_cannot_write(raw_client):
    make(raw_client, title="Secret", visibility="private", join_policy="approval")
    bring(raw_client, "secret", 2, "bob")
    with ws(raw_client, "secret") as alice:
        alice.send_json({"content": "old news"})
        next_text(alice)
    assert call(raw_client, "DELETE", "/rooms/secret/members/2", 1, "alice", params={"reason": "spam"}).status_code == 204
    assert [m["content"] for m in texts(raw_client, "secret", 2, "bob")] == ["old news"]
    kicked = [m for m in call(raw_client, "GET", "/rooms/secret/members", 1, "alice").json() if m["user_id"] == 2][0]
    assert kicked["status"] == "kicked" and kicked["status_reason"] == "spam"
    assert refused(raw_client, "secret").reason == "You are not a member of this room"
    assert call(raw_client, "POST", "/rooms/secret/members", 1, "alice", json={"user_id": 2}).status_code == 201  # the owner brings them back


def test_a_banned_person_cannot_read_or_come_back_until_the_ban_is_lifted(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"status": "banned", "reason": "rude"})
    assert call(raw_client, "GET", "/rooms/residents/messages", 2, "bob").status_code == 403
    assert call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={}).status_code == 403
    call(raw_client, "POST", "/rooms/residents/leave", 2, "bob")  # does not undo it
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"status": "joined"}).status_code == 200
    assert call(raw_client, "GET", "/rooms/residents/messages", 2, "bob").status_code == 200


def test_a_room_left_can_be_taken_off_my_list_without_touching_the_room(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "POST", "/rooms/residents/hide", 2, "bob").status_code == 409  # still in it
    call(raw_client, "POST", "/rooms/residents/leave", 2, "bob")
    assert call(raw_client, "POST", "/rooms/residents/hide", 2, "bob").status_code == 204
    assert call(raw_client, "GET", "/rooms", 2, "bob", params={"scope": "past"}).json() == []
    assert call(raw_client, "GET", "/rooms/residents", 1, "alice").json()["members"] == 1  # the room is as it was
    assert [m["status"] for m in call(raw_client, "GET", "/rooms/residents/members", 1, "alice").json() if m["user_id"] == 2] == ["left"]
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/leave", 2, "bob")
    assert [r["slug"] for r in call(raw_client, "GET", "/rooms", 2, "bob", params={"scope": "past"}).json()] == ["residents"]  # back after a new stay


def test_a_person_who_left_cannot_be_put_back_by_the_owner(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/leave", 2, "bob")
    assert call(raw_client, "PATCH", "/rooms/residents/members/2", 1, "alice", json={"status": "joined"}).status_code == 409


def test_a_deleted_room_is_hidden_and_its_owner_can_restore_it_with_everything_in_it(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents") as alice:
        alice.send_json({"content": "keep me"})
        next_text(alice)
    call(raw_client, "DELETE", "/rooms/residents", 1, "alice")
    assert call(raw_client, "GET", "/rooms/residents/messages", 2, "bob").status_code == 404
    assert call(raw_client, "POST", "/rooms/residents/join", 3, "carol", json={}).status_code == 404
    taken = call(raw_client, "POST", "/rooms", 3, "carol", json={"title": "Residents", "slug": "residents"})
    assert taken.status_code == 409  # the address stays taken
    assert [r["slug"] for r in call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "past"}).json()] == ["residents"]
    assert call(raw_client, "PATCH", "/rooms/residents", 2, "bob", json={"state": "open"}).status_code == 404
    restored = call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"state": "open"})
    assert restored.json()["state"] == "open" and restored.json()["members"] == 2
    assert [m["content"] for m in texts(raw_client, "residents", 2, "bob")] == ["keep me"]
    assert [r["slug"] for r in call(raw_client, "GET", "/rooms", 3, "carol").json()] == ["residents"]


def test_the_owner_leaving_hands_the_room_over(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    call(raw_client, "POST", "/rooms/residents/transfer", 1, "alice", json={"user_id": 2})
    call(raw_client, "POST", "/rooms/residents/leave", 1, "alice")
    room = call(raw_client, "GET", "/rooms/residents", 2, "bob").json()
    assert room["user_id"] == 2
    people = {m["user_id"]: (m["role"], m["status"]) for m in call(raw_client, "GET", "/rooms/residents/members", 2, "bob").json()}
    assert people == {1: ("member", "left"), 2: ("owner", "joined")}  # the one who left is still on the list of the owner


def test_only_open_rooms_count_towards_the_limit_of_rooms_one_person_may_own(raw_client):
    for n in range(20):
        make(raw_client, title=f"Room {n}")
    assert call(raw_client, "POST", "/rooms", 1, "alice", json={"title": "One more"}).status_code == 409
    call(raw_client, "PATCH", "/rooms/room-0", 1, "alice", json={"state": "closed"})
    call(raw_client, "DELETE", "/rooms/room-1", 1, "alice")
    assert call(raw_client, "POST", "/rooms", 1, "alice", json={"title": "One more"}).status_code == 201
    assert call(raw_client, "POST", "/rooms", 1, "alice", json={"title": "And another"}).status_code == 201
    assert call(raw_client, "POST", "/rooms", 1, "alice", json={"title": "Too many"}).status_code == 409


def test_a_deleted_room_can_be_removed_for_good_and_its_address_is_free_again(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents") as alice:
        alice.send_json({"content": "gone soon"})
        next_text(alice)
    assert call(raw_client, "DELETE", "/rooms/residents", 1, "alice", params={"permanent": "true"}).status_code == 409  # delete it first
    call(raw_client, "DELETE", "/rooms/residents", 1, "alice")
    assert call(raw_client, "DELETE", "/rooms/residents", 2, "bob", params={"permanent": "true"}).status_code == 404  # hidden for others
    assert call(raw_client, "DELETE", "/rooms/residents", 1, "alice", params={"permanent": "true"}).status_code == 204
    assert call(raw_client, "GET", "/rooms/residents", 1, "alice").status_code == 404
    assert call(raw_client, "GET", "/rooms", 1, "alice", params={"scope": "past"}).json() == []
    with raw_client.app.state.session_factory() as session:
        from api.chat.models import Message, RoomMember

        assert [session.query(t).count() for t in (Message, RoomMember)] == [0, 0]
    assert make(raw_client)["slug"] == "residents"  # the address is free


def test_the_members_list_has_everyone_who_was_ever_in_the_room_with_their_status(raw_client):
    make(raw_client, title="Group")  # with approval: the owner lets each one in (see `call`)
    for uid, name in ((2, "bob"), (3, "carol"), (4, "dave")):
        call(raw_client, "POST", "/rooms/group/join", uid, name, json={})
    call(raw_client, "POST", "/rooms/group/leave", 2, "bob")
    call(raw_client, "DELETE", "/rooms/group/members/3", 1, "alice")
    call(raw_client, "PATCH", "/rooms/group/members/4", 1, "alice", json={"status": "banned", "reason": "rude"})
    call(raw_client, "POST", "/rooms", 5, "erin", json={"title": "x"})
    seen = {m["username"]: m["status"] for m in call(raw_client, "GET", "/rooms/group/members", 1, "alice").json()}
    assert seen == {"alice": "joined", "bob": "left", "carol": "kicked", "dave": "banned"}
    plain = call(raw_client, "GET", "/rooms/group/members", 4, "dave")  # banned: reads nothing
    assert plain.status_code == 200  # the list is of people, the ban only closes the messages
    assert all(m["status_reason"] is None for m in plain.json())  # a reason is for the owner


def test_a_game_is_for_the_members_of_an_open_room_and_its_code_is_worked_out_not_kept(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    assert call(raw_client, "POST", "/rooms/residents/meeting", 1, "alice").status_code in (404, 405)  # the meeting is its own module now
    game = call(raw_client, "POST", "/rooms/residents/game", 2, "bob").json()
    assert len(game["code"]) == 5 and game["code"].isalpha() and game["code"].isupper()
    assert game["seats"] == 5  # two members: the least the game allows
    assert call(raw_client, "POST", "/rooms/residents/game", 1, "alice").json() == game
    room = call(raw_client, "GET", "/rooms/residents", 3, "carol").json()  # a reader who is not a member
    assert "settings" not in room and "werewolfCode" not in str(room)
    assert call(raw_client, "POST", "/rooms/residents/game", 3, "carol").status_code == 403
    call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"state": "closed"})
    assert call(raw_client, "POST", "/rooms/residents/game", 1, "alice").status_code == 409


def test_the_conversation_says_who_opened_a_game_once_in_a_while(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    with ws(raw_client, "residents", 2, "bob") as bob:
        call(raw_client, "POST", "/rooms/residents/game", 2, "bob")
        game = next_message(bob)
        assert (game["content"], game["username"]) == ("game:bob", "system")
        call(raw_client, "POST", "/rooms/residents/game", 1, "alice")  # a moment later: not said again
    said = [(m["content"], m["username"]) for m in call(raw_client, "GET", "/rooms/residents/messages").json() if m["kind"] == "system"]
    assert said == [("joined:bob", "system"), ("game:bob", "system")]


def test_search_does_not_mind_case_or_accents_in_vietnamese(raw_client):
    make(raw_client, title="Nhóm Đồng Hương", category="Mua bán")
    call(raw_client, "POST", "/rooms/nhom-dong-huong/join", 2, "bob", json={})
    with ws(raw_client, "nhom-dong-huong", 2, "bob") as bob:
        bob.send_json({"content": "Ai cần chiếc XE ĐẠP cũ không?"})
        next_text(bob)

    def found(words):
        rooms = call(raw_client, "GET", "/rooms", 3, "carol", params={"q": words}).json()
        return [r["slug"] for r in rooms], (rooms[0]["hit"] if rooms else None)

    for words in ("dong huong", "ĐỒNG HƯƠNG", "nhom", "mua ban", "xe dap", "Xe Đạp"):
        assert found(words)[0] == ["nhom-dong-huong"], words
    slugs, hit = found("xe dap")
    assert hit["message"]["content"] == "Ai cần chiếc XE ĐẠP cũ không?" and hit["fields"] == []  # said, not named
    assert found("dong huong")[1]["fields"] == ["title"]
    assert found("khong co")[0] == []
    assert found("50%")[0] == []  # a % is a letter, not a wildcard


def test_someone_sent_away_cannot_open_the_game_of_the_room_any_more(raw_client):
    make(raw_client)
    for uid, name in ((2, "bob"), (3, "carol")):
        call(raw_client, "POST", "/rooms/residents/join", uid, name, json={})
    game = call(raw_client, "POST", "/rooms/residents/game", 2, "bob").json()
    assert call(raw_client, "POST", "/rooms/residents/game", 3, "carol").json() == game  # the code of a room does not change
    call(raw_client, "DELETE", "/rooms/residents/members/2", 1, "alice")
    assert call(raw_client, "POST", "/rooms/residents/game", 2, "bob").status_code == 403  # but it is for the members only


def test_writing_is_throttled_per_person_and_reading_is_not(raw_client):
    from sn_shared.limits import UserRateLimiter

    raw_client.app.state.write_throttle = UserRateLimiter(max_events=3, window=60)
    make(raw_client)
    for _ in range(2):
        assert call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"title": "Again"}).status_code == 200
    blocked = call(raw_client, "PATCH", "/rooms/residents", 1, "alice", json={"title": "Again"})
    assert blocked.status_code == 429 and blocked.json()["detail"] == "Too many requests"
    assert all(call(raw_client, "GET", "/rooms/residents", 1, "alice").status_code == 200 for _ in range(10))
    assert call(raw_client, "POST", "/rooms", 2, "bob", json={"title": "Bob room"}).status_code == 201  # another person


def test_a_deleted_room_goes_for_good_only_when_its_owner_asks_after_deleting_it(raw_client):
    from api.chat.models import Message, Room

    make(raw_client, title="Old one")
    make(raw_client, title="Kept one")
    assert call(raw_client, "DELETE", "/rooms/old-one?permanent=true", 1, "alice").status_code == 409  # delete it first
    call(raw_client, "DELETE", "/rooms/old-one", 1, "alice")
    assert call(raw_client, "DELETE", "/rooms/old-one?permanent=true", 1, "alice").status_code == 204
    with raw_client.app.state.session_factory() as session:
        assert sorted(r.slug for r in session.query(Room)) == ["kept-one"]
        assert session.query(Message).filter(Message.room_id.is_not(None)).count() == 0


# ---- the Werewolf game of a room is made here, not by the page ---------------------------------------------------


def seat_of(client, code, uid, name):
    state = call(client, "GET", f"/werewolf/rooms/{code}", uid, name).json()["state"]
    return state["you"], state


def test_the_game_of_a_room_is_made_by_the_first_member_and_joined_by_the_others(raw_client):
    make(raw_client, title="Game night")
    for uid, name in ((2, "bob"), (3, "carol")):
        call(raw_client, "POST", "/rooms/game-night/join", uid, name, json={})
    first = call(raw_client, "POST", "/rooms/game-night/game", 2, "bob")
    assert first.status_code == 200, first.text
    code = first.json()["code"]
    you, state = seat_of(raw_client, code, 2, "bob")
    assert you["username"] == "bob" and you["seat"] == 1  # the one who made it is its host
    assert state["title"] == "Game night" and state["isHost"] is True and len(state["members"]) == 5
    assert call(raw_client, "POST", "/rooms/game-night/game", 2, "bob").json()["code"] == code  # again: the same game
    assert call(raw_client, "POST", "/rooms/game-night/game", 3, "carol").json()["code"] == code
    humans = [m["name"] for m in seat_of(raw_client, code, 3, "carol")[1]["members"] if not m["isBot"]]
    assert sorted(humans) == ["bob", "carol"]
    assert call(raw_client, "GET", "/werewolf/rooms", 4, "dave").json() == []  # not listed: only those who are in the room get its code


def test_nobody_is_seated_in_a_game_that_has_started_or_is_full_or_when_they_hold_too_many(raw_client):
    make(raw_client, title="Busy")
    for n in range(2, 6):  # five in the room: the game has five seats
        call(raw_client, "POST", "/rooms/busy/join", n, f"user{n}", json={})
    code = call(raw_client, "POST", "/rooms/busy/game", 1, "alice").json()["code"]
    for n in range(2, 6):
        assert call(raw_client, "POST", "/rooms/busy/game", n, f"user{n}").status_code == 200
    call(raw_client, "POST", "/rooms/busy/join", 6, "user6", json={})  # a sixth person comes after the game was made: the game grows a seat
    sixth = call(raw_client, "POST", "/rooms/busy/game", 6, "user6")
    assert sixth.status_code == 200 and sixth.json()["code"] == code
    assert len(seat_of(raw_client, code, 6, "user6")[1]["members"]) == 6
    assert call(raw_client, "POST", f"/werewolf/rooms/{code}/start", 1, "alice").status_code == 200
    call(raw_client, "POST", "/rooms/busy/join", 7, "user7", json={})
    started = call(raw_client, "POST", "/rooms/busy/game", 7, "user7")
    assert started.status_code == 409 and started.json()["detail"] == "The game has started"
    # a person may hold a seat in a limited number of games (a small limit keeps the test short)
    raw_client.app.state.ww_store.max_rooms_per_user = 3
    for title in ("One", "Two", "Three"):
        make(raw_client, title=title, uid=9, name="zed")
        assert call(raw_client, "POST", f"/rooms/{title.lower()}/game", 9, "zed").status_code == 200
    make(raw_client, title="Four", uid=9, name="zed")
    many = call(raw_client, "POST", "/rooms/four/game", 9, "zed")
    assert many.status_code == 409 and many.json()["detail"] == "You are in too many games"


def test_the_game_is_only_for_the_members_of_an_open_room(raw_client):
    make(raw_client, title="Closed one")
    assert call(raw_client, "POST", "/rooms/closed-one/game", 3, "carol").status_code == 403  # not a member
    call(raw_client, "PATCH", "/rooms/closed-one", 1, "alice", json={"state": "closed"})
    assert call(raw_client, "POST", "/rooms/closed-one/game", 1, "alice").status_code == 409


def test_the_game_of_a_room_goes_when_the_room_is_deleted(raw_client):
    make(raw_client)
    call(raw_client, "POST", "/rooms/residents/join", 2, "bob", json={})
    code = call(raw_client, "POST", "/rooms/residents/game", 2, "bob").json()["code"]
    assert raw_client.app.state.ww_store.get(code) is not None
    assert call(raw_client, "DELETE", "/rooms/residents", 1, "alice").status_code == 204
    assert raw_client.app.state.ww_store.get(code) is None  # its seats must not count toward the limit of games of its players
