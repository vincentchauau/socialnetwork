import pytest
from starlette.websockets import WebSocketDisconnect

from sn_shared import COOKIE_NAME, create_token
from tests.conftest import ALLOWED_ORIGIN, auth_cookie, ws_headers


def test_ws_without_cookie_is_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/general", headers={"Origin": "http://localhost:8080"}):
            pass


def test_ws_from_foreign_origin_is_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/general", headers=ws_headers(origin="http://evil.example")
        ):
            pass


def test_ws_invalid_room_name_is_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/bad room!", headers=ws_headers()):
            pass


def test_message_is_broadcast_to_everyone_in_room(client):
    with client.websocket_connect("/ws/general", headers=ws_headers(1, "alice")) as alice, \
         client.websocket_connect("/ws/general", headers=ws_headers(2, "bob")) as bob:
        alice.send_json({"content": "hello"})

        for socket in (alice, bob):
            received = socket.receive_json()
            assert received["content"] == "hello"
            assert received["username"] == "alice"
            assert received["room"] == "general"


def test_message_does_not_leak_to_other_rooms(client):
    with client.websocket_connect("/ws/a", headers=ws_headers(1, "alice")) as in_a, \
         client.websocket_connect("/ws/b", headers=ws_headers(2, "bob")) as in_b:
        in_a.send_json({"content": "only for a"})
        in_a.receive_json()
        in_b.send_json({"content": "only for b"})
        assert in_b.receive_json()["content"] == "only for b"


def test_username_comes_from_token_not_payload(client):
    with client.websocket_connect("/ws/general", headers=ws_headers(1, "alice")) as alice:
        alice.send_json({"content": "hi", "username": "admin"})
        assert alice.receive_json()["username"] == "alice"


@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "   "}, {"content": "x" * 2001}, {}])
def test_invalid_message_returns_error_and_keeps_connection(client, payload):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_json(payload)
        assert "error" in alice.receive_json()
        alice.send_json({"content": "still alive"})
        assert alice.receive_json()["content"] == "still alive"


def test_history_returns_messages_oldest_first(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        for text in ("one", "two", "three"):
            alice.send_json({"content": text})
            alice.receive_json()

    response = client.get("/rooms/general/messages", headers=auth_cookie())

    assert response.status_code == 200
    assert [m["content"] for m in response.json()] == ["one", "two", "three"]


def test_history_respects_limit_and_keeps_latest(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        for text in ("one", "two", "three"):
            alice.send_json({"content": text})
            alice.receive_json()

    response = client.get("/rooms/general/messages?limit=2", headers=auth_cookie())

    assert [m["content"] for m in response.json()] == ["two", "three"]


def test_history_requires_auth(client):
    assert client.get("/rooms/general/messages").status_code == 401


def test_history_rejects_invalid_room(client):
    response = client.get("/rooms/bad room!/messages", headers=auth_cookie())
    assert response.status_code == 422


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ws_without_origin_is_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/general", headers=auth_cookie()):
            pass


def test_ws_with_expired_cookie_is_rejected(client):
    expired = {"Cookie": f"{COOKIE_NAME}={create_token(1, 'alice', ttl_seconds=-5)}", "Origin": ALLOWED_ORIGIN}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/general", headers=expired):
            pass


def test_ws_with_tampered_cookie_is_rejected(client):
    tampered = {"Cookie": f"{COOKIE_NAME}={create_token(1, 'alice')}x", "Origin": ALLOWED_ORIGIN}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/general", headers=tampered):
            pass


def test_ws_closes_when_token_expires(client):
    short_lived = {"Cookie": f"{COOKIE_NAME}={create_token(1, 'alice', ttl_seconds=1)}", "Origin": ALLOWED_ORIGIN}
    with client.websocket_connect("/ws/general", headers=short_lived) as socket:
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_non_json_frame_returns_error_and_keeps_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_text("this is not json")
        assert "error" in alice.receive_json()
        alice.send_json({"content": "still alive"})
        assert alice.receive_json()["content"] == "still alive"


def test_binary_frame_returns_error_and_keeps_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_bytes(b"\x00\x01")
        assert "error" in alice.receive_json()
        alice.send_json({"content": "still alive"})
        assert alice.receive_json()["content"] == "still alive"


def test_oversized_frame_closes_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_text("x" * (8 * 1024 + 1))
        with pytest.raises(WebSocketDisconnect):
            alice.receive_json()


def test_message_of_exactly_2000_characters_is_accepted(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_json({"content": "x" * 2000})
        assert len(alice.receive_json()["content"]) == 2000


def test_flooding_closes_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        with pytest.raises(WebSocketDisconnect):
            for _ in range(60):
                alice.send_json({"content": "spam"})
                alice.receive_json()
