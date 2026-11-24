"""Search, create, read, update and delete of the messages and the members of a room, over HTTP."""

from tests.chat.test_room_api import call, make, texts


def join(client, slug, uid, name):
    assert call(client, "POST", f"/rooms/{slug}/join", uid, name, json={}).status_code in (200, 201)


def send(client, slug, content, uid=1, name="alice", **extra):
    return call(client, "POST", f"/rooms/{slug}/messages", uid, name, json={"content": content, **extra})


class TestSendMessage:
    def test_a_member_sends_by_http_and_it_is_in_the_history(self, raw_client):
        slug = make(raw_client)["slug"]
        sent = send(raw_client, slug, "  Xin chào cả nhà  ")
        assert sent.status_code == 201
        assert sent.json()["content"] == "Xin chào cả nhà" and sent.json()["edited_at"] is None
        assert [m["content"] for m in texts(raw_client, slug)] == ["Xin chào cả nhà"]

    def test_a_reply_points_at_the_message_it_answers_and_a_gone_target_is_dropped(self, raw_client):
        slug = make(raw_client)["slug"]
        first = send(raw_client, slug, "one").json()
        assert send(raw_client, slug, "two", reply_to=first["id"]).json()["reply_to_id"] == first["id"]
        assert send(raw_client, slug, "three", reply_to=99999).json()["reply_to_id"] is None

    def test_rules_of_the_room_hold_over_http_too(self, raw_client):
        slug = make(raw_client)["slug"]
        assert send(raw_client, slug, "hi", uid=2, name="bob").status_code in (403, 404)  # not a member
        join(raw_client, slug, 2, "bob")
        call(raw_client, "PATCH", f"/rooms/{slug}/members/2", json={"muted": True})
        assert send(raw_client, slug, "hi", uid=2, name="bob").status_code == 403  # muted
        call(raw_client, "PATCH", f"/rooms/{slug}", json={"state": "closed"})
        assert send(raw_client, slug, "late").status_code == 403

    def test_empty_and_too_long_messages_are_refused(self, raw_client):
        slug = make(raw_client)["slug"]
        assert send(raw_client, slug, "   ").status_code == 422
        assert send(raw_client, slug, "").status_code == 422
        assert send(raw_client, slug, "x" * 2001).status_code == 422


class TestSearchMessages:
    def test_finds_messages_by_words_ignoring_case_and_accents(self, raw_client):
        slug = make(raw_client)["slug"]
        for text in ("Tranh sơn dầu hoàng hôn", "Giá bán 500 USD", "Ảnh chụp ĐÀ LẠT"):
            send(raw_client, slug, text)
        found = lambda q: [m["content"] for m in call(raw_client, "GET", f"/rooms/{slug}/messages", params={"q": q}).json()]
        assert found("hoang hon") == ["Tranh sơn dầu hoàng hôn"]
        assert found("da lat") == ["Ảnh chụp ĐÀ LẠT"]
        assert found("USD") == ["Giá bán 500 USD"]
        assert found("không có") == []

    def test_percent_and_underscore_are_ordinary_letters_and_deleted_ones_are_not_found(self, raw_client):
        slug = make(raw_client)["slug"]
        keep = send(raw_client, slug, "100% sure").json()
        gone = send(raw_client, slug, "100 sure").json()
        call(raw_client, "DELETE", f"/rooms/{slug}/messages/{gone['id']}")
        hits = call(raw_client, "GET", f"/rooms/{slug}/messages", params={"q": "%"}).json()
        assert [m["id"] for m in hits] == [keep["id"]]
        assert call(raw_client, "GET", f"/rooms/{slug}/messages", params={"q": "sure"}).json()[0]["id"] == keep["id"]

    def test_only_a_member_who_may_read_searches(self, raw_client):
        slug = make(raw_client, visibility="private", join_policy="approval")["slug"]
        send(raw_client, slug, "secret")
        assert call(raw_client, "GET", f"/rooms/{slug}/messages", 2, "bob", params={"q": "secret"}).status_code in (403, 404)


class TestEditMessage:
    def test_the_author_edits_and_it_is_marked_edited(self, raw_client):
        slug = make(raw_client)["slug"]
        message = send(raw_client, slug, "helo").json()
        done = call(raw_client, "PATCH", f"/rooms/{slug}/messages/{message['id']}", json={"content": " hello "})
        assert done.status_code == 200 and done.json()["content"] == "hello" and done.json()["edited_at"]
        assert texts(raw_client, slug)[0]["content"] == "hello"

    def test_nobody_else_edits_not_even_the_owner(self, raw_client):
        slug = make(raw_client)["slug"]
        join(raw_client, slug, 2, "bob")
        message = send(raw_client, slug, "mine", uid=2, name="bob").json()
        assert call(raw_client, "PATCH", f"/rooms/{slug}/messages/{message['id']}", json={"content": "changed"}).status_code == 403
        assert texts(raw_client, slug)[0]["content"] == "mine"

    def test_a_deleted_or_empty_or_long_edit_is_refused(self, raw_client):
        slug = make(raw_client)["slug"]
        message = send(raw_client, slug, "one").json()
        assert call(raw_client, "PATCH", f"/rooms/{slug}/messages/{message['id']}", json={"content": "  "}).status_code == 422
        assert call(raw_client, "PATCH", f"/rooms/{slug}/messages/{message['id']}", json={"content": "x" * 2001}).status_code == 422
        call(raw_client, "DELETE", f"/rooms/{slug}/messages/{message['id']}")
        assert call(raw_client, "PATCH", f"/rooms/{slug}/messages/{message['id']}", json={"content": "back"}).status_code == 404

    def test_system_lines_cannot_be_edited(self, raw_client):
        slug = make(raw_client)["slug"]
        join(raw_client, slug, 2, "bob")  # a line says that bob came
        system = next(m for m in call(raw_client, "GET", f"/rooms/{slug}/messages").json() if m["kind"] == "system")
        assert call(raw_client, "PATCH", f"/rooms/{slug}/messages/{system['id']}", json={"content": "x"}).status_code == 403


class TestMembers:
    def test_search_by_name_and_by_status(self, raw_client):
        slug = make(raw_client)["slug"]
        join(raw_client, slug, 2, "Bình")
        join(raw_client, slug, 3, "carol")
        names = lambda **params: [m["username"] for m in call(raw_client, "GET", f"/rooms/{slug}/members", params=params).json()]
        assert names(q="binh") == ["Bình"]
        assert names(q="CAR") == ["carol"]
        assert names(q="zzz") == []
        call(raw_client, "DELETE", f"/rooms/{slug}/members/3")
        assert names(status="kicked") == ["carol"]
        assert set(names(status="joined")) == {"alice", "Bình"}

    def test_a_bad_status_is_a_validation_error(self, raw_client):
        slug = make(raw_client)["slug"]
        assert call(raw_client, "GET", f"/rooms/{slug}/members", params={"status": "nope"}).status_code == 422

    def test_read_one_member(self, raw_client):
        slug = make(raw_client)["slug"]
        join(raw_client, slug, 2, "bob")
        one = call(raw_client, "GET", f"/rooms/{slug}/members/2")
        assert one.status_code == 200 and one.json()["username"] == "bob" and one.json()["status"] == "joined"
        assert call(raw_client, "GET", f"/rooms/{slug}/members/999").status_code == 404

    def test_a_pending_request_is_read_only_by_the_owner(self, raw_client):
        slug = make(raw_client, join_policy="approval")["slug"]
        join(raw_client, slug, 2, "bob")  # pending
        assert call(raw_client, "GET", f"/rooms/{slug}/members/2").json()["status"] == "pending"
        join(raw_client, slug, 3, "carol")
        assert call(raw_client, "GET", f"/rooms/{slug}/members/2", 3, "carol").status_code in (403, 404)


class TestAddMember:
    def know(self, client, uid, name):
        """A person is found by name when they have an account (a row of `users`)."""
        from sn_shared.testing import add_person

        add_person(client.app.state.session_factory, uid, name)

    def test_the_owner_adds_a_person_by_name_ignoring_case(self, raw_client):
        slug = make(raw_client)["slug"]
        self.know(raw_client, 2, "Bob")
        added = call(raw_client, "POST", f"/rooms/{slug}/members", json={"username": "bOB"})
        assert added.status_code == 201 and added.json()["username"] == "Bob" and added.json()["status"] == "joined"
        assert call(raw_client, "POST", f"/rooms/{slug}/members", json={"username": "bob"}).status_code == 409  # already in

    def test_by_id_and_the_way_back_for_someone_who_was_sent_away(self, raw_client):
        slug = make(raw_client)["slug"]
        self.know(raw_client, 2, "bob")
        join(raw_client, slug, 2, "bob")
        call(raw_client, "DELETE", f"/rooms/{slug}/members/2")
        names = lambda status: [m["username"] for m in call(raw_client, "GET", f"/rooms/{slug}/members", params={"status": status}).json()]
        assert names("kicked") == ["bob"]
        back = call(raw_client, "POST", f"/rooms/{slug}/members", json={"user_id": 2})
        assert back.status_code == 201 and names("kicked") == [] and "bob" in names("joined")

    def test_a_banned_person_is_not_added_but_unbanned(self, raw_client):
        slug = make(raw_client)["slug"]
        self.know(raw_client, 2, "bob")
        join(raw_client, slug, 2, "bob")
        call(raw_client, "PATCH", f"/rooms/{slug}/members/2", json={"status": "banned"})
        assert call(raw_client, "POST", f"/rooms/{slug}/members", json={"username": "bob"}).status_code == 409
        assert call(raw_client, "PATCH", f"/rooms/{slug}/members/2", json={"status": "joined"}).json()["status"] == "joined"

    def test_unknown_people_wrong_bodies_and_people_outside_the_room_are_refused(self, raw_client):
        slug = make(raw_client)["slug"]
        assert call(raw_client, "POST", f"/rooms/{slug}/members", json={"username": "nobody"}).status_code == 404
        assert call(raw_client, "POST", f"/rooms/{slug}/members", json={}).status_code == 422
        assert call(raw_client, "POST", f"/rooms/{slug}/members", json={"username": "a", "user_id": 2}).status_code == 422
        join(raw_client, slug, 2, "bob")
        self.know(raw_client, 3, "carol")
        invited = call(raw_client, "POST", f"/rooms/{slug}/members", 2, "bob", json={"username": "carol"})
        assert invited.status_code == 201 and invited.json()["status"] == "pending"  # a member invites: the owner of a room with approval decides
        self.know(raw_client, 4, "dave")
        assert call(raw_client, "POST", f"/rooms/{slug}/members", 4, "dave", json={"username": "carol"}).status_code in (403, 404)  # not in the room

    def test_a_full_room_and_a_direct_chat_refuse(self, raw_client):
        slug = make(raw_client, capacity=2)["slug"]
        join(raw_client, slug, 2, "bob")
        self.know(raw_client, 3, "carol")
        assert call(raw_client, "POST", f"/rooms/{slug}/members", json={"username": "carol"}).status_code == 409
        dm = call(raw_client, "POST", "/dm", json={"user_id": 2}).json()["slug"]
        assert call(raw_client, "POST", f"/rooms/{dm}/members", json={"username": "carol"}).status_code in (403, 409)


def test_a_room_carries_the_name_of_its_owner_in_the_list_and_on_its_own(raw_client):
    slug = make(raw_client, name="alice")["slug"] if False else make(raw_client)["slug"]
    assert call(raw_client, "GET", f"/rooms/{slug}").json()["owner_name"] == "alice"
    listed = {r["slug"]: r for r in call(raw_client, "GET", "/rooms", params={"scope": "mine"}).json()}
    assert listed[slug]["owner_name"] == "alice"
    join(raw_client, slug, 2, "bob")
    call(raw_client, "POST", f"/rooms/{slug}/transfer", json={"user_id": 2})
    assert call(raw_client, "GET", f"/rooms/{slug}", 2, "bob").json()["owner_name"] == "bob"
