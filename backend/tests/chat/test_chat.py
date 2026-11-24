import pytest
from sn_shared import COOKIE_NAME, create_token
from starlette.websockets import WebSocketDisconnect

from tests.chat.conftest import ALLOWED_ORIGIN, auth_cookie, frame_of, next_message, ws_headers


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
            received = next_message(socket)
            assert received["content"] == "hello"
            assert received["username"] == "alice"
            assert "room" not in received  # the room of a message is the one the socket is of


def test_message_does_not_leak_to_other_rooms(client):
    with client.websocket_connect("/ws/a", headers=ws_headers(1, "alice")) as in_a, \
         client.websocket_connect("/ws/b", headers=ws_headers(2, "bob")) as in_b:
        in_a.send_json({"content": "only for a"})
        next_message(in_a)
        in_b.send_json({"content": "only for b"})
        assert next_message(in_b)["content"] == "only for b"


def test_username_comes_from_token_not_payload(client):
    with client.websocket_connect("/ws/general", headers=ws_headers(1, "alice")) as alice:
        alice.send_json({"content": "hi", "username": "admin"})
        assert next_message(alice)["username"] == "alice"


@pytest.mark.parametrize("payload", [{"content": ""}, {"content": "   "}, {"content": "x" * 2001}, {}])
def test_invalid_message_returns_error_and_keeps_connection(client, payload):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_json(payload)
        assert frame_of(alice, "error")["error"]
        alice.send_json({"content": "still alive"})
        assert next_message(alice)["content"] == "still alive"


def test_history_returns_messages_oldest_first(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        for text in ("one", "two", "three"):
            alice.send_json({"content": text})
            next_message(alice)

    response = client.get("/rooms/general/messages", headers=auth_cookie())

    assert response.status_code == 200
    assert [m["content"] for m in response.json()] == ["one", "two", "three"]


def test_history_respects_limit_and_keeps_latest(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        for text in ("one", "two", "three"):
            alice.send_json({"content": text})
            next_message(alice)

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
            next_message(socket)


def test_non_json_frame_returns_error_and_keeps_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_text("this is not json")
        assert frame_of(alice, "error")["error"]
        alice.send_json({"content": "still alive"})
        assert next_message(alice)["content"] == "still alive"


def test_binary_frame_returns_error_and_keeps_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_bytes(b"\x00\x01")
        assert frame_of(alice, "error")["error"]
        alice.send_json({"content": "still alive"})
        assert next_message(alice)["content"] == "still alive"


def test_oversized_frame_closes_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_text("x" * (8 * 1024 + 1))
        with pytest.raises(WebSocketDisconnect):
            next_message(alice)


def test_message_of_exactly_2000_characters_is_accepted(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        alice.send_json({"content": "x" * 2000})
        assert len(next_message(alice)["content"]) == 2000


def test_flooding_closes_connection(client):
    with client.websocket_connect("/ws/general", headers=ws_headers()) as alice:
        with pytest.raises(WebSocketDisconnect):
            for _ in range(60):
                alice.send_json({"content": "spam"})
                next_message(alice)


def _forged(algorithm: str, key) -> str:
    import time

    import jwt
    from sn_shared.jwtkeys import get_verification_keys

    claims = {"iss": "sn-center", "sub": "1", "username": "alice", "exp": int(time.time()) + 60}
    return jwt.encode(claims, key, algorithm=algorithm, headers={"kid": next(iter(get_verification_keys()))})


def test_ws_with_hs256_token_is_rejected(client):
    headers = {"Cookie": f"{COOKIE_NAME}={_forged('HS256', 'x' * 40)}", "Origin": ALLOWED_ORIGIN}
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/general", headers=headers):
            pass


def test_http_rejects_a_token_signed_by_another_private_key(client):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    forged = _forged("EdDSA", Ed25519PrivateKey.generate())
    assert client.get("/rooms/general/messages", headers={"Cookie": f"{COOKIE_NAME}={forged}"}).status_code == 401
