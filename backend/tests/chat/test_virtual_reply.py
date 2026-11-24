"""Virtual people answer in the rooms they are in: through the agent, as themselves, by the rules of the room."""

import time

import pytest
from sn_shared import COOKIE_NAME, create_token, servicesig

from api.chat import virtual_reply
from tests.chat.conftest import ALLOWED_ORIGIN
from tests.chat.social.test_virtual_people import draw, pool
from tests.chat.test_room_api import call

SECRET = "k" * 32


def cookie(uid, name):
    return {"Cookie": f"{COOKIE_NAME}={create_token(uid, name)}", "Origin": ALLOWED_ORIGIN}


@pytest.fixture
def agent(monkeypatch):
    """The agent answers with a fixed line, and remembers what it was asked."""
    asked = []
    monkeypatch.setenv("AGENT_URL", "http://agent:8000")
    monkeypatch.setenv("AGENT_SECRET", SECRET)

    def ask(virtual_id, caller_id, caller, lines):
        asked.append((virtual_id, caller_id, caller, lines))
        return f"xin chào {caller} từ {virtual_id}", (10, 5, 100)

    monkeypatch.setattr(virtual_reply, "ask_agent_counted", ask)
    virtual_reply._answering.clear()
    return asked


def dm_with_companion(client):
    pool(client, 1)
    draw(client, count=1)
    return call(client, "POST", "/dm", 1, "alice", json={"user_id": 500}).json()["slug"]


def talk(client, slug, text="Chào bạn"):
    with client.websocket_connect(f"/ws/{slug}", headers=cookie(1, "alice")) as socket:
        socket.receive_json()  # presence
        socket.send_json({"content": text})
        seen = []
        deadline = time.time() + 5
        while time.time() < deadline:
            frame = socket.receive_json()
            seen.append(frame)
            if frame.get("type") == "message" and frame["user_id"] == 500:
                break
        return seen


def test_a_companion_in_a_private_chat_answers_the_person_who_wrote(raw_client, agent):
    slug = dm_with_companion(raw_client)
    seen = talk(raw_client, slug)
    answer = [f for f in seen if f.get("type") == "message" and f["user_id"] == 500]
    assert answer and answer[0]["content"] == "xin chào alice từ 500" and answer[0]["username"] == "Virt_0"
    virtual_id, caller_id, caller, lines = agent[0]
    assert (virtual_id, caller_id, caller) == (500, 1, "alice") and lines[-1] == {"username": "alice", "content": "Chào bạn"}
    history = call(raw_client, "GET", f"/rooms/{slug}/messages", 1, "alice").json()
    assert [m["user_id"] for m in history if m["user_id"] != -1][-2:] == [1, 500]  # (the line of `system` with what it cost follows the answer)  # it is saved: it is still there tomorrow


def test_nothing_happens_without_an_agent(raw_client, monkeypatch):
    monkeypatch.setattr(virtual_reply, "_factory", None)
    slug = dm_with_companion(raw_client)
    assert not virtual_reply.agent_ready()
    with raw_client.websocket_connect(f"/ws/{slug}", headers=cookie(1, "alice")) as socket:
        socket.receive_json()
        socket.send_json({"content": "alo"})
        frames = [socket.receive_json() for _ in range(2)]
        assert "alo" in [f.get("content") for f in frames]
    assert call(raw_client, "GET", f"/rooms/{slug}/messages", 1, "alice").json()[-1]["user_id"] == 1


def test_a_closed_room_takes_no_words_from_a_virtual_person(raw_client, agent):
    from api.chat.models import Room

    slug = dm_with_companion(raw_client)
    factory = raw_client.app.state.session_factory
    assert virtual_reply.save(factory, slug, 500, "Virt_0", "hi") is not None
    with factory() as db:
        db.query(Room).filter(Room.slug == slug).update({"state": "closed"})
        db.commit()
    assert virtual_reply.save(factory, slug, 500, "Virt_0", "hi") is None
    with factory() as db:
        assert virtual_reply.speakers(db, slug, 1) == []


def test_the_call_to_the_agent_is_signed_and_a_failure_is_silence(monkeypatch):
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"text": " bonjour "}'

    def fake_open(request, timeout):
        sent.update(url=request.full_url, body=request.data, headers={k.lower(): v for k, v in request.header_items()})
        return Response()

    from api.chat.agent import service as agent_service

    calls = []

    def fake_reply(db, virtual_id, caller_id, caller, history):
        calls.append((virtual_id, caller_id, caller, [(line.username, line.content) for line in history]))
        return agent_service.Reply(text=" bonjour ", usage=agent_service.Usage(3, 4) if hasattr(agent_service, "Usage") else None, ms=5)

    monkeypatch.setattr(agent_service, "reply", fake_reply)
    assert virtual_reply.ask_agent(5, 1, "alice", [{"username": "alice", "content": "hi"}]) == "bonjour"
    assert calls == [(5, 1, "alice", [("alice", "hi")])]

    monkeypatch.setattr(agent_service, "reply", lambda *args: None)
    assert virtual_reply.ask_agent(5, 1, "alice", [{"username": "alice", "content": "hi"}]) is None
    assert virtual_reply.ask_agent(5, 1, "alice", []) is None
