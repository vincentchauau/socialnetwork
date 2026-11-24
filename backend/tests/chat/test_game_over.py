"""The Werewolf tells the chat that the game of a room is over: a line of `system` in the room, once, from a signed call only."""

import json

import pytest

from api.chat import service
from sn_shared import servicesig
from tests.chat.test_room_api import call, make

SECRET = "s" * 32
CODE = "ABCDE"
SCOPE = "POST /internal/game-over"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("WEREWOLF_SECRET", SECRET)
    monkeypatch.setattr(service, "game_code", lambda room: CODE)  # the code of a game is worked out from the room: here every room has this one


def with_game(client, slug):
    """The room has a game (its code is worked out, nothing to set up)."""
    assert call(client, "GET", f"/rooms/{slug}").status_code == 200


def tell(client, payload, secret=SECRET, scope=SCOPE):
    body = json.dumps(payload).encode()
    return client.post("/internal/game-over", content=body, headers=servicesig.sign(secret, body, scope) if secret else {})


def lines(client, slug):
    return [m["content"] for m in call(client, "GET", f"/rooms/{slug}/messages", 1, "alice").json() if m["kind"] == "system"]


def test_the_end_of_the_game_is_said_in_the_room_of_that_game(raw_client):
    slug = make(raw_client)["slug"]
    with_game(raw_client, slug)
    before = lines(raw_client, slug)
    assert tell(raw_client, {"code": CODE, "winner": "WOLF", "days": 4, "size": 7}).status_code == 204
    assert lines(raw_client, slug) == before + ["game_over:WOLF:4"]


def test_a_game_that_is_not_of_any_room_is_ignored(raw_client):
    slug = make(raw_client)["slug"]
    before = lines(raw_client, slug)
    assert tell(raw_client, {"code": "ZZZZZ", "winner": "WOLF", "days": 1, "size": 5}).status_code == 204
    assert lines(raw_client, slug) == before


def test_an_unknown_winner_reads_as_a_draw(raw_client):
    slug = make(raw_client)["slug"]
    with_game(raw_client, slug)
    tell(raw_client, {"code": CODE, "winner": "<b>x</b>", "days": 3, "size": 5})
    assert lines(raw_client, slug)[-1] == "game_over:DRAW:3"


def test_only_a_call_signed_for_this_call_is_obeyed(raw_client):
    slug = make(raw_client)["slug"]
    with_game(raw_client, slug)
    before = lines(raw_client, slug)
    payload = {"code": CODE, "winner": "WOLF", "days": 4, "size": 7}
    assert tell(raw_client, payload, secret=None).status_code == 401
    assert tell(raw_client, payload, secret="x" * 32).status_code == 401
    assert tell(raw_client, payload, scope="POST /internal/ensure").status_code == 401  # a signature taken from another call
    assert lines(raw_client, slug) == before


def test_a_body_that_is_not_one_is_refused_after_the_signature(raw_client):
    for payload in ({}, {"code": CODE, "winner": "WOLF", "days": -1, "size": 1}, {"code": CODE, "winner": "WOLF", "days": 1, "size": 1, "x": 1}):
        assert tell(raw_client, payload).status_code == 422


def cards(client, slug):
    import json as _json

    return [_json.loads(m["content"]) for m in call(client, "GET", f"/rooms/{slug}/messages", 1, "alice").json() if m["kind"] == "card"]


def test_every_role_and_what_all_the_players_saw_come_as_one_card(raw_client):
    slug = make(raw_client)["slug"]
    with_game(raw_client, slug)
    payload = {"code": CODE, "winner": "WOLF", "days": 2, "size": 3,
               "roles": ["An: Sói · Giết", "Bình: Người · Không có chức năng"], "seen": ["💀 An chết", "⚖️ Không ai bị treo cổ."]}
    assert tell(raw_client, payload).status_code == 204
    card = cards(raw_client, slug)[-1]
    assert card["type"] == "detail" and card["actions"] == []
    assert card["lines"] == ["Vai của mọi người", "An: Sói · Giết", "Bình: Người · Không có chức năng", "Diễn biến", "💀 An chết", "⚖️ Không ai bị treo cổ."]
    assert lines(raw_client, slug)[-1] == "game_over:WOLF:2"


def test_a_long_log_is_cut_at_its_end_to_fit_a_message(raw_client):
    import json as _json

    slug = make(raw_client)["slug"]
    with_game(raw_client, slug)
    seen = [f"dòng {i} " + "x" * 190 for i in range(120)]
    assert tell(raw_client, {"code": CODE, "winner": "DRAW", "days": 9, "size": 9, "roles": ["An: Người"], "seen": seen}).status_code == 204
    card = cards(raw_client, slug)[-1]
    assert card["lines"][0] == "Vai của mọi người" and card["lines"][2] == "Diễn biến" and card["lines"][3].startswith("dòng 0 ")
    assert 5 < len(card["lines"]) < 40 and len(_json.dumps(card, ensure_ascii=False)) < 6000


def test_a_game_without_anything_to_show_says_only_that_it_is_over(raw_client):
    slug = make(raw_client)["slug"]
    with_game(raw_client, slug)
    before = len(cards(raw_client, slug))
    tell(raw_client, {"code": CODE, "winner": "WOLF", "days": 1, "size": 3})
    assert len(cards(raw_client, slug)) == before
