"""The Werewolf game is a module of its own: the chat asks it for the game of a room with a signed call (`sn_shared.servicesig`).

`WEREWOLF_URL` is where the module is (`http://127.0.0.1:8000/werewolf` in the host) and `WEREWOLF_SECRET` signs the body (the same on both sides).
In tests `app.state.werewolf_call` is replaced by a function that reaches the game without a network.
"""

import json
import os
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException, status

from sn_shared import servicesig

TIMEOUT_SECONDS = 5.0
UNAVAILABLE = "The game is not available"


def _send(method: str, path: str, payload: dict | None) -> None:
    url, secret = os.environ.get("WEREWOLF_URL", "").rstrip("/"), os.environ.get("WEREWOLF_SECRET", "")
    if not url or len(secret) < servicesig.MIN_SECRET_CHARS:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)
    body = json.dumps(payload).encode() if payload is not None else b""
    request = urllib.request.Request(f"{url}{path}", data=body or None, headers={"Content-Type": "application/json", **servicesig.sign(secret, body, f"{method} {path}")}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310 - the address of our own game module
            return
    except urllib.error.HTTPError as error:  # the reasons the game gives (full, started, too many...) are told as they are
        try:
            detail = json.loads(error.read()).get("detail", UNAVAILABLE)
        except (ValueError, AttributeError):
            detail = UNAVAILABLE
        raise HTTPException(error.code, detail) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from None


def call(app: FastAPI, method: str, path: str, payload: dict | None = None) -> None:
    """Make the call (blocking: run it in a thread). Raises the HTTPException the game answered with."""
    sender = getattr(app.state, "werewolf_call", None) or _send
    sender(method, path, payload)


def ensure_game(app: FastAPI, user_id: int, username: str, code: str, title: str, seats: int, bot_names: list[tuple[str, str]]) -> None:
    call(app, "POST", "/internal/ensure", {"code": code, "title": title, "seats": seats, "user_id": user_id, "username": username, "bot_names": [list(pair) for pair in bot_names]})


def drop_game(app: FastAPI, code: str) -> None:
    call(app, "DELETE", f"/internal/rooms/{code}")
