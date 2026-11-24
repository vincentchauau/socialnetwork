"""Tools act with the token of the person who asked; writes need the confirmation of that person."""

import json

import pytest
from sn_shared import servicesig

from api.chat.agent import tools

CALLS: list[tuple[str, str, dict, bytes | None]] = []


def fake_http(answers):
    def http(method, url, headers, body):
        CALLS.append((method, url, headers, body))
        for needle, reply in answers.items():
            if needle in url:
                return reply
        return 404, None

    return http


@pytest.fixture(autouse=True)
def clean():
    CALLS.clear()


def post_tool(client, **fields):
    body = json.dumps({"caller_id": 1, "token": "tok", "confirmed": False, "args": {}, **fields}).encode()
    return client.post("/tools", content=body)


def test_a_search_lists_what_the_service_found_with_the_token_of_the_caller(client):
    client.app.state.http = fake_http({"/products": (200, {"items": [{"name": "Đèn bàn", "price_cents": 12000, "seller_username": "bob"}], "next_cursor": None})})
    card = post_tool(client, tool="market.search", args={"q": "đèn"}).json()["card"]
    assert card["type"] == "list" and card["items"][0] == {"title": "Đèn bàn", "subtitle": "120.00 · bob", "href": "/market"}
    method, url, headers, _ = CALLS[0]
    assert method == "GET" and "q=%C4%91%C3%A8n" in url and headers["Cookie"] == "sn_token=tok"


def test_a_write_without_confirmation_only_asks_and_touches_nothing(client):
    client.app.state.http = fake_http({})
    card = post_tool(client, tool="market.sell", args={"name": "Bàn", "price_cents": 5000}).json()["card"]
    assert card["type"] == "confirm" and card["tool"] == "market.sell" and card["args"] == {"name": "Bàn", "price_cents": 5000}
    assert "Bàn" in card["summary"] and CALLS == []


def test_a_confirmed_write_is_done_for_the_caller_and_says_what_was_refused(client):
    client.app.state.http = fake_http({"/products": (201, {"name": "Bàn", "price_cents": 5000})})
    card = post_tool(client, tool="market.sell", args={"name": "Bàn", "price_cents": 5000}, confirmed=True).json()["card"]
    assert card["type"] == "done" and "Bàn" in card["summary"]
    assert json.loads(CALLS[0][3]) == {"name": "Bàn", "price_cents": 5000, "stock": 1} and CALLS[0][2]["Cookie"] == "sn_token=tok"
    client.app.state.http = fake_http({"/apply": (409, {"detail": "You already applied to this job"})})
    refused = post_tool(client, tool="jobs.apply", args={"job_id": 3}, confirmed=True).json()["card"]
    assert refused == {"type": "error", "summary": "You already applied to this job"}


def test_nothing_runs_without_a_token_and_a_down_service_is_an_error_card(client):
    client.app.state.http = fake_http({})
    assert post_tool(client, tool="jobs.apply", args={"job_id": 3}, confirmed=True, token="").json()["card"]["type"] == "error"

    def down(*_):
        raise tools.ToolError("That service is not answering right now")

    client.app.state.http = down
    assert post_tool(client, tool="market.search", args={"q": "x"}).json()["card"]["summary"].startswith("That service")


def test_unknown_tools_bad_arguments_and_unsigned_calls_are_refused(client):
    assert post_tool(client, tool="shell.run", args={}).status_code == 422
    assert post_tool(client, tool="market.search", args={"q": ""}).status_code == 422
    assert post_tool(client, tool="market.sell", args={"name": "x", "price_cents": 0}).status_code == 422
    assert post_tool(client, tool="market.search", args={"q": "x", "evil": 1}).status_code == 422


def test_the_long_text_of_a_service_is_cut_and_only_a_few_items_are_shown(client):
    many = [{"name": "n" * 500, "price_cents": 1, "seller_username": "s"} for _ in range(9)]
    client.app.state.http = fake_http({"/products": (200, {"items": many})})
    card = post_tool(client, tool="market.search", args={"q": "n"}).json()["card"]
    assert len(card["items"]) == tools.MAX_ITEMS and all(len(item["title"]) <= tools.TEXT_CHARS for item in card["items"])


def test_the_services_are_looked_for_in_the_core_unless_told_otherwise(monkeypatch):
    monkeypatch.delenv("MARKET_URL", raising=False)
    assert tools.base("market") == "http://127.0.0.1:8000/market"
    monkeypatch.setenv("JOB_URL", "http://jobs.example/")
    assert tools.base("job") == "http://jobs.example"
