import json
import os

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from sn_shared import COOKIE_NAME, create_token

from api.chat.main import create_app  # noqa: E402
from api import werewolf as game  # noqa: E402
from api.werewolf.db import Base as GameBase  # noqa: E402
from api.werewolf.main import create_app as create_game  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sn_shared import servicesig  # noqa: E402

ALLOWED_ORIGIN = "http://localhost:8080"

_MINTED: dict[int, str] = {}  # the people a test made a token for: each gets a row of `users` (the one place names are read from)


def seed_minted(test_client) -> None:
    """Give every person a token was minted for a row of `users`, unless there is one: a name is read from there, not from the token."""
    from sn_shared.directory import Person

    done = test_client.__dict__.setdefault("_seeded_people", set())
    fresh = {(uid, name) for uid, name in _MINTED.items()} - done
    if not fresh:
        return
    with test_client.app.state.session_factory() as session:
        for uid, name in sorted(fresh):
            if session.get(Person, uid) is None:
                session.add(Person(user_id=uid, username=name))
        session.commit()
    done.update(fresh)


def _seeding(test_client) -> None:
    for method in ("request", "websocket_connect"):
        original = getattr(test_client, method)

        def wrapped(*args, _original=original, **kwargs):
            seed_minted(test_client)
            return _original(*args, **kwargs)

        setattr(test_client, method, wrapped)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    install_test_keys(monkeypatch)
    monkeypatch.setenv("ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    monkeypatch.setenv("WEREWOLF_SECRET", "w" * 32)
    from api.chat import service

    service._ANNOUNCED.clear()  # "said a moment ago" is kept in memory: each test starts with nothing said


@pytest.fixture
def raw_client(tmp_path):
    """The app as it is: a socket needs a room that exists and a member. A file database, so that the test thread and
    the app's threads each have their own connection (one shared in-memory connection mixes their transactions)."""
    _MINTED.clear()
    application = create_app(f"sqlite:///{tmp_path / 'chat.db'}")
    # The game of a room is a module of its own: the chat asks it with a signed call. Here the game is an app of its own too, and its routes are also
    # mounted on the chat app (under `/werewolf`, sharing its state) so that a test can look at the game of a room through the same client.
    game_app = create_game(f"sqlite:///{tmp_path / 'game.db'}")
    for name in ("ww_hub", "ww_limits", "ww_store"):
        setattr(application.state, name, getattr(game_app.state, name))
    GameBase.metadata.create_all(application.state.session_factory.kw["bind"])
    application.include_router(game.router, prefix="/werewolf")
    application.include_router(game.ws_router, prefix="/werewolf")

    def ask_game(method: str, path: str, payload: dict | None) -> None:
        body = json.dumps(payload).encode() if payload is not None else b""
        sent = game_client.request(method, path, content=body, headers=servicesig.sign("w" * 32, body, f"{method} {path}"))
        if sent.status_code >= 400:
            raise HTTPException(sent.status_code, sent.json().get("detail", "The game is not available"))

    application.state.werewolf_call = ask_game
    with TestClient(application) as test_client, TestClient(game_app) as game_client:
        _seeding(test_client)
        yield test_client


def ensure_member(test_client, slug: str, user_id: int, username: str) -> None:
    """Make the room (public, open, owned by whoever came first) and the user an active member of it."""

    from api.chat.models import Room, RoomMember
    from api.chat.service import room_by_slug

    _MINTED[user_id] = username
    seed_minted(test_client)

    with test_client.app.state.session_factory() as session:
        room = room_by_slug(session, slug)
        if room is None:
            room = Room(slug=slug, title=slug, user_id=user_id)
            session.add(room)
            session.flush()
        if session.get(RoomMember, (room.id, user_id)) is None:
            session.add(RoomMember(room_id=room.id, user_id=user_id))
        session.commit()
        test_client.app.state.public_slugs.add(slug)  # the lobby names public rooms only


@pytest.fixture
def client(raw_client):
    """`raw_client`, where opening a socket in a room first makes the room and the user's membership (the way rooms
    used to appear): the tests of messages, presence and limits need not set a room up each time."""
    from sn_shared.security import payload_from_cookies

    original = raw_client.websocket_connect

    def connect(url, *args, **kwargs):
        headers = kwargs.get("headers") or {}
        try:
            token = headers["Cookie"].split("=", 1)[1]
            user = payload_from_cookies({COOKIE_NAME: token})
            slug = str(url).split("/ws/", 1)[1]
            if "/" not in slug and "?" not in slug and "bad" not in slug:
                ensure_member(raw_client, slug, user.user_id, user.username)
        except Exception:  # a socket that must be refused is refused for its own reason
            pass
        return original(url, *args, **kwargs)

    raw_client.websocket_connect = connect  # type: ignore[method-assign]
    return raw_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    _MINTED[user_id] = username
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


def ws_headers(user_id: int = 1, username: str = "alice", origin: str = ALLOWED_ORIGIN):
    return {**auth_cookie(user_id, username), "Origin": origin}


def frame_of(socket, kind: str) -> dict:
    """Next frame of the given type, skipping presence/system frames."""
    while True:
        received = socket.receive_json()
        if received.get("type") == kind:
            return received


def next_message(socket) -> dict:
    return frame_of(socket, "message")
