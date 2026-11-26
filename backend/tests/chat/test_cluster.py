"""Two copies of the chat behind one gateway: they tell each other what happens, and they agree on who is where."""

import time

import fakeredis
import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from api.chat import cluster as clustering
from api.chat.main import create_app
from api.chat.presence import Presence
from tests.chat.conftest import ALLOWED_ORIGIN, _seeding
from tests.chat.test_room_api import call
from tests.chat.test_virtual_reply import cookie


def copy_of_chat(path, server):
    app = create_app(f"sqlite:///{path}")
    app.state.cluster_client = fakeredis.aioredis.FakeRedis(server=server)
    client = TestClient(app)
    _seeding(client)  # a name is read from `users`: the people a token was minted for get a row there, as in the other tests
    return client


@pytest.fixture
def two(tmp_path):
    """Two copies of the chat, one database, one Redis."""
    server = fakeredis.FakeServer()
    with copy_of_chat(tmp_path / "chat.db", server) as first, copy_of_chat(tmp_path / "chat.db", server) as second:
        yield first, second


def make_room(client, slug="party"):
    # a room with approval has an owner who can ban: bob asks, alice lets him in
    assert call(client, "POST", "/rooms", 1, "alice", json={"slug": slug, "title": "Party", "visibility": "public", "join_policy": "approval"}).status_code == 201
    assert call(client, "POST", f"/rooms/{slug}/join", 2, "bob", json={}).status_code == 200
    assert call(client, "PATCH", f"/rooms/{slug}/members/2", 1, "alice", json={"status": "joined"}).status_code == 200


def frames_until(socket, wanted, seconds=5):
    seen, deadline = [], time.time() + seconds
    while time.time() < deadline:
        frame = socket.receive_json()
        seen.append(frame)
        if wanted(frame):
            return seen
    raise AssertionError(f"not seen in {seconds}s: {seen}")


def test_a_message_written_on_one_copy_reaches_a_socket_on_the_other(two):
    first, second = two
    make_room(first)
    with second.websocket_connect("/ws/party", headers=cookie(2, "bob")) as bob:
        frames_until(bob, lambda f: f.get("type") == "presence")
        with first.websocket_connect("/ws/party", headers=cookie(1, "alice")) as alice:
            frames_until(alice, lambda f: f.get("type") == "presence" and f["total"] == 2)  # alice sees bob, who is on the other copy
            alice.send_json({"content": "hello across"})
            got = frames_until(bob, lambda f: f.get("type") == "message" and f.get("content") == "hello across")
            assert got[-1]["username"] == "alice"


def test_presence_is_the_whole_chat_not_one_copy(two):
    first, second = two
    make_room(first)
    with second.websocket_connect("/ws/party", headers=cookie(2, "bob")) as bob:
        frames_until(bob, lambda f: f.get("type") == "presence")
        with first.websocket_connect("/ws/party", headers=cookie(1, "alice")) as alice:
            frames_until(bob, lambda f: f.get("type") == "presence" and f["total"] == 2)  # bob is told alice came, on the other copy
            names = {m["username"] for m in frames_until(alice, lambda f: f.get("type") == "presence" and f["total"] == 2)[-1]["members"]}
            assert names == {"alice", "bob"}
            assert first.app.state.online_users() >= {1, 2} and second.app.state.online_users() >= {1, 2}


def test_a_ban_on_one_copy_closes_the_socket_on_the_other(two):
    first, second = two
    make_room(first)
    with second.websocket_connect("/ws/party", headers=cookie(2, "bob")) as bob:
        frames_until(bob, lambda f: f.get("type") == "presence")
        banned = call(first, "PATCH", "/rooms/party/members/2", 1, "alice", json={"status": "banned"})
        assert banned.status_code == 200
        with pytest.raises(Exception):  # the socket is closed by the server
            frames_until(bob, lambda f: False, seconds=5)


def test_a_new_public_room_on_one_copy_is_known_to_the_other(two):
    first, second = two
    assert "fresh" not in second.app.state.public_slugs
    assert call(first, "POST", "/rooms", 1, "alice", json={"slug": "fresh", "title": "Fresh", "visibility": "public"}).status_code == 201
    deadline = time.time() + 5
    while "fresh" not in second.app.state.public_slugs and time.time() < deadline:
        time.sleep(0.05)
    assert "fresh" in second.app.state.public_slugs


def test_a_copy_that_leaves_takes_its_picture_away(two):
    first, second = two
    key = clustering.PRESENCE_KEY + first.app.state.cluster.replica
    client = fakeredis.FakeRedis(server=first.app.state.cluster.client_revocation.connection_pool.connection_kwargs["server"])
    deadline = time.time() + 5
    while not client.exists(key) and time.time() < deadline:
        time.sleep(0.05)
    assert client.exists(key) and client.ttl(key) <= clustering.PRESENCE_TTL_SECONDS


def test_without_the_setting_a_chat_is_one_copy_and_asks_nothing_of_redis(raw_client):
    assert raw_client.app.state.cluster is None and raw_client.app.state.hub.cluster is None
    assert not clustering.enabled()


def test_presence_merges_what_the_other_copies_see():
    presence = Presence()
    presence.join("a", 1, "alice")
    presence.set_remote({"a": {2: "bob"}, "b": {3: "carol"}})
    members, total = presence.members("a")
    assert [m["username"] for m in members] == ["alice", "bob"] and total == 2
    assert {entry["room"] for entry in presence.rooms()} == {"a", "b"}
    assert presence.refusal("b", 9) is None
    assert ALLOWED_ORIGIN
