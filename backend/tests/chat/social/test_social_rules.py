"""What the social side does to the chat: a block stops a message, friends write to each other at once."""

from tests.chat.social.people import join, make_people
from tests.chat.test_room_api import call, make


def test_friends_can_message_each_other_at_once_without_sharing_a_room(raw_client):
    make_people(raw_client)
    call(raw_client, "POST", "/friends/2", 1, "alice")
    call(raw_client, "POST", "/friends/1/accept", 2, "bob")
    opened = call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 2})
    assert opened.status_code == 200, opened.text
    assert opened.json()["title"] == "bob" and opened.json()["kind"] == "dm" and opened.json()["members"] == 2  # open for both
    again = call(raw_client, "POST", "/dm", 2, "bob", json={"user_id": 1})
    assert again.json()["slug"] == opened.json()["slug"]  # the same chat from the other side
    assert call(raw_client, "POST", "/dm", 1, "alice", json={"user_id": 99}).status_code == 404  # nobody
