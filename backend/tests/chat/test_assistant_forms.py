"""Forms and buttons in cards: sent or pressed only by the person the card is for, the work done by the agent with their token."""

import json
import time

import pytest

from api.chat import assistant, virtual_reply
from tests.chat.test_assistant import cards, write
from tests.chat.test_virtual_reply import SECRET, dm_with_companion
from tests.chat.test_room_api import call

FORM = {"type": "form", "tool": "jobs.post", "title": "Post a job", "fields": [{"name": "title", "label": "Title", "kind": "text", "required": True}], "args": {}, "submit": "Post"}
LIST = {
    "type": "list", "title": "Applicants",
    "items": [{"title": "bob", "actions": [
        {"label": "Shortlist", "tool": "jobs.setstatus", "args": {"application_id": 1, "status": "shortlisted"}, "run": "do"},
        {"label": "Hire", "tool": "jobs.setstatus", "args": {"application_id": 1, "status": "hired"}, "run": "ask"},
        {"label": "Applicants", "tool": "jobs.applicants", "args": {"job_id": 2}, "run": "open"},
    ]}],
}


@pytest.fixture
def agent(monkeypatch):
    """The agent: a form for `jobs.post`, a list for `jobs.applicants`; a sent form is posted unless its title is `bad`."""
    seen = []
    monkeypatch.setenv("AGENT_URL", "http://agent:8000")
    monkeypatch.setenv("AGENT_SECRET", SECRET)

    def ask(tool, args, caller_id, token, confirmed):
        seen.append((tool, args, caller_id, token, confirmed))
        if tool == "jobs.post":
            if not confirmed:
                return dict(FORM)
            return {"type": "error", "summary": "title: too short"} if args.get("title") == "bad" else {"type": "done", "summary": "Posted job #1", "href": "/job/employer"}
        if tool == "jobs.applicants":
            return LIST
        if tool == "jobs.setstatus":
            return {"type": "done", "summary": "Application #1 is now shortlisted"} if confirmed else {"type": "confirm", "tool": tool, "args": args, "summary": "Mark application #1 as hired"}
        return None

    monkeypatch.setattr(assistant, "ask_tool", ask)
    monkeypatch.setattr(virtual_reply, "ask_agent_counted", lambda *a: None)
    virtual_reply._answering.clear()
    return seen


def last_card(client, slug):
    card = cards(client, slug)[-1]
    return card, json.loads(card["content"])


def test_a_form_is_for_the_person_who_asked_and_a_good_form_is_posted_as_them(raw_client, agent):
    slug = dm_with_companion(raw_client)
    write(raw_client, slug, "/postjob")
    card, body = last_card(raw_client, slug)
    assert body["type"] == "form" and body["status"] == "pending" and body["for"] == 1
    sent = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 1, "alice", json={"values": {"title": "Python dev", "company": "Acme"}})
    assert sent.status_code == 200 and json.loads(sent.json()["content"])["status"] == "done"
    tool, args, caller, token, confirmed = agent[-1]
    assert (tool, args, caller, confirmed) == ("jobs.post", {"title": "Python dev", "company": "Acme"}, 1, True) and token
    assert json.loads(cards(raw_client, slug)[-1]["content"])["summary"] == "Posted job #1"
    again = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 1, "alice", json={"values": {"title": "x"}})
    assert again.status_code == 409  # one form, one time


def test_a_form_that_does_not_fit_stays_open_with_the_reason(raw_client, agent):
    slug = dm_with_companion(raw_client)
    write(raw_client, slug, "/postjob")
    card, _ = last_card(raw_client, slug)
    first = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 1, "alice", json={"values": {"title": "bad"}})
    body = json.loads(first.json()["content"])
    assert body["status"] == "pending" and body["error"] == "title: too short" and len(cards(raw_client, slug)) == 1
    ok = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 1, "alice", json={"values": {"title": "good"}})
    assert json.loads(ok.json()["content"])["status"] == "done" and "error" not in json.loads(ok.json()["content"])


def test_the_values_of_a_form_cannot_replace_what_the_form_fixed_and_cannot_be_huge(raw_client, agent, monkeypatch):
    slug = dm_with_companion(raw_client)
    fixed = {**FORM, "tool": "market.edit", "args": {"product_id": 4}}
    monkeypatch.setattr(assistant, "ask_tool", lambda tool, args, *rest: dict(fixed) if tool == "market.edit" and not rest[-1] else (agent.append((tool, args)) or {"type": "done", "summary": "Saved"}))
    write(raw_client, slug, "/editproduct 4")
    card, _ = last_card(raw_client, slug)
    call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 1, "alice", json={"values": {"product_id": 99, "name": "x"}})
    assert agent[-1] == ("market.edit", {"product_id": 4, "name": "x"})
    write(raw_client, slug, "/editproduct 4")
    card, _ = last_card(raw_client, slug)
    huge = call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 1, "alice", json={"values": {"name": "x" * 30_000}})
    assert huge.status_code == 422


def test_only_the_person_a_form_is_for_may_send_it_and_a_button_press_needs_a_real_button(raw_client, agent):
    slug = dm_with_companion(raw_client)
    write(raw_client, slug, "/postjob")
    card, _ = last_card(raw_client, slug)
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/submit", 2, "bob", json={"values": {"title": "x"}}).status_code in (403, 404)
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/act", 1, "alice", json={"action": 0}).status_code == 404  # a form has no buttons
    text = call(raw_client, "GET", f"/rooms/{slug}/messages", 1, "alice").json()[0]
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{text['id']}/submit", 1, "alice", json={"values": {}}).status_code == 404


def test_buttons_open_do_or_ask_as_the_card_says_and_the_browser_cannot_change_what_they_do(raw_client, agent):
    slug = dm_with_companion(raw_client)
    write(raw_client, slug, "/applicants 2")
    card, body = last_card(raw_client, slug)
    assert body["for"] == 1 and body["items"][0]["actions"][0]["label"] == "Shortlist"
    path = f"/rooms/{slug}/cards/{card['id']}/act"
    done = call(raw_client, "POST", path, 1, "alice", json={"item": 0, "action": 0})
    assert json.loads(done.json()["content"])["summary"] == "Application #1 is now shortlisted"
    assert agent[-1][:2] == ("jobs.setstatus", {"application_id": 1, "status": "shortlisted"}) and agent[-1][4] is True
    asked = call(raw_client, "POST", path, 1, "alice", json={"item": 0, "action": 1})
    ask_card = json.loads(asked.json()["content"])
    assert ask_card["type"] == "confirm" and ask_card["status"] == "pending" and ask_card["for"] == 1 and agent[-1][4] is False  # nothing done yet
    opened = call(raw_client, "POST", path, 1, "alice", json={"item": 0, "action": 2})
    assert json.loads(opened.json()["content"])["type"] == "list" and agent[-1][4] is False
    assert call(raw_client, "POST", path, 1, "alice", json={"item": 0, "action": 7}).status_code == 404
    assert call(raw_client, "POST", path, 1, "alice", json={"item": 5, "action": 0}).status_code == 404
    assert call(raw_client, "POST", path, 2, "bob", json={"item": 0, "action": 0}).status_code in (403, 404)
    assert call(raw_client, "POST", path, 1, "alice", json={"item": 0, "action": 0, "tool": "shell.run"}).status_code == 422  # nothing else is read


def test_a_card_without_buttons_has_nobody_it_is_for_and_cannot_be_pressed(raw_client, agent, monkeypatch):
    slug = dm_with_companion(raw_client)
    monkeypatch.setattr(assistant, "ask_tool", lambda *a: {"type": "list", "title": "t", "items": [{"title": "x"}]})
    write(raw_client, slug, "/cart")
    card, body = last_card(raw_client, slug)
    assert "for" not in body
    assert call(raw_client, "POST", f"/rooms/{slug}/cards/{card['id']}/act", 1, "alice", json={"item": 0, "action": 0}).status_code == 403
    time.sleep(0)


def test_commands_are_understood():
    assert assistant.parse("/face") == ("face.measure", {}) and assistant.parse("/measurements") == ("face.history", {})
    assert assistant.parse("/saved") == ("jobs.saved", {}) and assistant.parse("/profile") == ("jobs.profile", {}) and assistant.parse("/sales") == ("market.sales", {})
    assert assistant.parse("/job 3") == ("jobs.job", {"job_id": 3}) and assistant.parse("/editjob 3") == ("jobs.editpost", {"job_id": 3})
    assert assistant.parse("/pay 4") == ("market.pay", {"order_id": 4}) and assistant.parse("/review 2") == ("market.review", {"product_id": 2})
    assert assistant.parse("/clearmeasurements") == ("face.clear", {})
    assert assistant.parse("/myproducts") == ("market.mine", {}) and assistant.parse("/postjob") == ("jobs.post", {})
    assert assistant.parse("/editproduct 3") == ("market.edit", {"product_id": 3})
