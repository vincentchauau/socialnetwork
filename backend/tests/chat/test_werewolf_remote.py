"""The signed call of the chat to the game module (`werewolf_remote`), without a network."""

import io
import json
import urllib.error

import pytest
from fastapi import FastAPI, HTTPException

from api.chat import werewolf_remote
from sn_shared import servicesig

SECRET = "s" * 32


@pytest.fixture
def app():
    return FastAPI()


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("WEREWOLF_URL", "http://127.0.0.1:8000/werewolf/")
    monkeypatch.setenv("WEREWOLF_SECRET", SECRET)


class Answer:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_without_an_address_or_a_secret_the_game_is_not_available(app, monkeypatch):
    monkeypatch.delenv("WEREWOLF_URL", raising=False)
    monkeypatch.delenv("WEREWOLF_SECRET", raising=False)
    with pytest.raises(HTTPException) as caught:
        werewolf_remote.ensure_game(app, 1, "alice", "ABC", "Room", 6, [])
    assert caught.value.status_code == 503
    monkeypatch.setenv("WEREWOLF_URL", "http://x")
    monkeypatch.setenv("WEREWOLF_SECRET", "short")
    with pytest.raises(HTTPException):
        werewolf_remote.drop_game(app, "ABC")


def test_the_call_is_signed_and_goes_to_the_game_module(app, configured, monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen.update(url=request.full_url, method=request.get_method(), body=request.data, headers=dict(request.header_items()))
        return Answer()

    monkeypatch.setattr(werewolf_remote.urllib.request, "urlopen", urlopen)
    werewolf_remote.ensure_game(app, 7, "bob", "ABC", "Room", 6, [("Lan_Nguyen", "Lan Nguyen")])
    assert seen["url"] == "http://127.0.0.1:8000/werewolf/internal/ensure" and seen["method"] == "POST"
    assert json.loads(seen["body"]) == {"code": "ABC", "title": "Room", "seats": 6, "user_id": 7, "username": "bob", "bot_names": [["Lan_Nguyen", "Lan Nguyen"]]}
    headers = {key.lower(): value for key, value in seen["headers"].items()}
    assert servicesig.verify(SECRET, seen["body"], "POST /internal/ensure", headers["x-service-timestamp"], headers["x-service-signature"])
    werewolf_remote.drop_game(app, "ABC")
    assert seen["method"] == "DELETE" and seen["url"].endswith("/internal/rooms/ABC") and seen["body"] is None


def test_the_reasons_the_game_gives_are_told_as_they_are(app, configured, monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 409, "Conflict", {}, io.BytesIO(b'{"detail": "The game is full"}'))

    monkeypatch.setattr(werewolf_remote.urllib.request, "urlopen", refuse)
    with pytest.raises(HTTPException) as caught:
        werewolf_remote.ensure_game(app, 1, "alice", "ABC", "Room", 6, [])
    assert (caught.value.status_code, caught.value.detail) == (409, "The game is full")


def test_a_game_that_does_not_answer_is_not_available(app, configured, monkeypatch):
    def down(request, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(werewolf_remote.urllib.request, "urlopen", down)
    with pytest.raises(HTTPException) as caught:
        werewolf_remote.ensure_game(app, 1, "alice", "ABC", "Room", 6, [])
    assert caught.value.status_code == 503

    def broken(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "Oops", {}, io.BytesIO(b"<html>"))

    monkeypatch.setattr(werewolf_remote.urllib.request, "urlopen", broken)
    with pytest.raises(HTTPException) as caught:
        werewolf_remote.drop_game(app, "ABC")
    assert (caught.value.status_code, caught.value.detail) == (500, werewolf_remote.UNAVAILABLE)


def test_a_test_can_put_its_own_sender_in_place_of_the_network(app):
    calls = []
    app.state.werewolf_call = lambda method, path, payload: calls.append((method, path, payload))
    werewolf_remote.drop_game(app, "XYZ")
    assert calls == [("DELETE", "/internal/rooms/XYZ", None)]
