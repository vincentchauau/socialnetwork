"""The assistant of a room: /commands become cards written by a virtual person; a card that asks is answered by its person only."""

import json
import threading
import time

import pytest

from api.chat import assistant, virtual_reply
from api.chat.models import CARD_PREFIX
from tests.chat.social.test_virtual_people import draw, pool
from tests.chat.test_room_api import call
from tests.chat.test_virtual_reply import SECRET, cookie, dm_with_companion


@pytest.fixture
def tools(monkeypatch):
    """The agent answers a tool call with a card chosen by the test; the calls are remembered."""
    seen = []
    monkeypatch.setenv("AGENT_URL", "http://agent:8000")
    monkeypatch.setenv("AGENT_SECRET", SECRET)
    answers = {
        "market.search": {"type": "list", "title": "Market: lamp", "items": [{"title": "Lamp", "subtitle": "12.00 · bob", "href": "/market"}]},
        "market.sell": {"type": "confirm", "tool": "market.sell", "args": {"name": "Desk", "price_cents": 5000}, "summary": "List Desk for sale at 50.00"},
    }

    def ask(tool, args, caller_id, token, confirmed):
        seen.append((tool, args, caller_id, token, confirmed))
        if confirmed:
            return {"type": "done", "summary": "Listed Desk"}
        return answers.get(tool)

    monkeypatch.setattr(assistant, "ask_tool", ask)
    monkeypatch.setitem(assistant.SEARCHES, "market", "market.search")  # the market is paused: its search is switched on for these tests only
    monkeypatch.setattr(virtual_reply, "ask_agent_counted", lambda *a: None)  # no chit-chat in these tests
    virtual_reply._answering.clear()
    return seen


def receive(socket, seconds: float) -> dict:
    """The next frame, or a failure after `seconds`: a frame that never comes must fail the test, not hang it."""
    box: list = []
    reader = threading.Thread(target=lambda: box.append(socket.receive_json()), daemon=True)
    reader.start()
    reader.join(max(seconds, 0.1))
    if not box:
        raise AssertionError("no frame from the room in time")
    return box[0]


def write(client, slug, text):
    """Say `text` in the room and return the frames seen until a card from the virtual person (or the first error) arrives."""
    with client.websocket_connect(f"/ws/{slug}", headers=cookie(1, "alice")) as socket:
        socket.receive_json()
        socket.send_json({"content": text})
        seen = []
        deadline = time.time() + 5
        while time.time() < deadline:
            frame = receive(socket, deadline - time.time())
            seen.append(frame)
            if frame.get("type") == "error" or (frame.get("type") == "message" and frame.get("kind") == "card"):
                break
        return seen


def cards(client, slug):
    return [m for m in call(client, "GET", f"/rooms/{slug}/messages", 1, "alice").json() if m["kind"] == "card"]


def test_a_search_comes_back_as_a_card_written_by_the_virtual_person_with_the_token_of_the_caller(raw_client, tools):
    slug = dm_with_companion(raw_client)
    frames = write(raw_client, slug, "/market lamp")
    card = [f for f in frames if f.get("kind") == "card"][0]
    assert card["user_id"] == 500 and json.loads(card["content"])["items"][0]["title"] == "Lamp"
    tool, args, caller, token, confirmed = tools[0]
    assert (tool, args, caller, confirmed) == ("market.search", {"q": "lamp"}, 1, False) and token  # the token of alice, not stored
    assert [m["kind"] for m in call(raw_client, "GET", f"/rooms/{slug}/messages", 1, "alice").json()][-2:] == ["text", "card"]


def test_a_wrong_command_and_a_room_without_a_companion_get_a_clear_error(raw_client, tools):
    slug = dm_with_companion(raw_client)
    assert write(raw_client, slug, "/market")[-1]["error"] == assistant.USAGE
    call(raw_client, "POST", "/rooms", 1, "alice", json={"slug": "alone", "title": "Alone", "visibility": "public"})
    assert write(raw_client, "alone", "/market lamp")[-1]["error"] == assistant.NO_ASSISTANT
    assert tools == []


def test_an_agent_that_cannot_be_reached_gives_an_error_card_not_silence(raw_client, tools, monkeypatch):
    monkeypatch.setattr(assistant, "ask_tool", lambda *a: None)
    slug = dm_with_companion(raw_client)
    card = [f for f in write(raw_client, slug, "/market lamp") if f.get("kind") == "card"][0]
    assert json.loads(card["content"])["type"] == "error"


def ask_to_sell(client):
    slug = dm_with_companion(client)
    write(client, slug, "/sell Desk 50")
    return slug, cards(client, slug)[-1]


def test_a_card_that_asks_changes_nothing_until_its_person_confirms_once(raw_client, tools):
    slug, card = ask_to_sell(raw_client)
    body = json.loads(card["content"])
    assert body["type"] == "confirm" and body["status"] == "pending" and body["for"] == 1
    assert [t for t in tools if t[4]] == []  # nothing has been done
    done = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/confirm", 1, "alice")
    assert done.status_code == 200 and json.loads(done.json()["content"])["status"] == "done"
    confirmed = [t for t in tools if t[4]]
    assert len(confirmed) == 1 and confirmed[0][:3] == ("market.sell", {"name": "Desk", "price_cents": 5000}, 1)
    assert json.loads(cards(raw_client, slug)[-1]["content"]) == {"type": "done", "summary": "Listed Desk"}
    again = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/confirm", 1, "alice")
    assert again.status_code == 409 and len([t for t in tools if t[4]]) == 1  # a second click does nothing


def test_only_the_person_asked_may_answer_and_a_no_does_nothing(raw_client, tools):
    slug, card = ask_to_sell(raw_client)
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/confirm", 2, "bob").status_code in (403, 404)
    cancelled = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/cancel", 1, "alice")
    assert json.loads(cancelled.json()["content"])["status"] == "cancelled" and [t for t in tools if t[4]] == []
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/confirm", 1, "alice").status_code == 409


def test_a_card_that_does_not_ask_cannot_be_confirmed(raw_client, tools):
    slug = dm_with_companion(raw_client)
    write(raw_client, slug, "/market lamp")
    listing = cards(raw_client, slug)[-1]
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{listing['id']}/confirm", 1, "alice").status_code == 404
    text = call(raw_client, "GET", f"/rooms/{slug}/messages", 1, "alice").json()[0]
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{text['id']}/confirm", 1, "alice").status_code == 404


def test_a_failed_confirmation_says_so_and_cannot_be_repeated(raw_client, tools, monkeypatch):
    slug, card = ask_to_sell(raw_client)
    monkeypatch.setattr(assistant, "ask_tool", lambda *a: {"type": "error", "summary": "It was refused"})
    result = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/confirm", 1, "alice")
    assert json.loads(result.json()["content"])["status"] == "failed"
    assert json.loads(cards(raw_client, slug)[-1]["content"])["summary"] == "It was refused"


def test_a_long_card_is_cut_to_what_a_message_may_hold():
    card = {"type": "list", "title": "t", "items": [{"title": "x" * 400, "subtitle": "y" * 400, "href": "/m"} for _ in range(5)]}
    text = assistant.encode(card)
    assert len(text) <= assistant.CARD_CHARS + len(CARD_PREFIX) and json.loads(text.removeprefix(CARD_PREFIX))["items"]


def test_a_card_does_not_point_to_the_pages_of_the_old_apps():
    text = assistant.encode({"type": "list", "title": "t", "href": "/market", "items": [{"title": "x", "href": "/job", "subtitle": "s"}]})
    assert json.loads(text.removeprefix(CARD_PREFIX)) == {"type": "list", "title": "t", "items": [{"title": "x", "subtitle": "s"}]}
    assert "href" not in assistant.encode({"type": "done", "summary": "ok", "href": "/market"})


def test_lines_are_parsed_into_tools_and_everything_else_is_a_plain_message(monkeypatch):
    monkeypatch.setitem(assistant.SEARCHES, "market", "market.search")  # the market is paused: no search unless switched on
    assert assistant.parse("/market lamp") == ("market.search", {"q": "lamp"})
    assert assistant.parse("/market lamp")  # (the search is switched on here only)
    assert assistant.parse("/addcart 3 2") == ("market.addcart", {"product_id": 3, "quantity": 2})
    assert assistant.parse("/apply 4") == ("jobs.apply", {"job_id": 4})
    assert assistant.parse("/sell desk 5") == ("market.sell", {"name": "desk", "price_cents": 500})
    for bad in ("/market", "/sell desk", "/sell 5", "/apply x", "/apply 0", "/apply", "/cart now", "/addcart", "/addcart x", "/addcart 1 0", "/addcart 1 100"):
        assert assistant.parse(bad) == ("", {}), bad
    assert assistant.parse("hello there") is None
