"""The Werewolf tells the chat that a game of one of its rooms is over, with a signed call (`sn_shared.servicesig`).

`CHAT_URL` is where the chat is (`http://127.0.0.1:8000/chat` in the host) and `WEREWOLF_SECRET` signs the body (the same on both sides).
It is only a line in the conversation: when the call fails the game is not harmed, the failure is logged and that is all.
In tests `app.state.chat_call` is replaced by a function that reaches the chat without a network.
"""

import json
import logging
import os
import urllib.error
import urllib.request

from fastapi import FastAPI

from sn_shared import servicesig

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0
GAME_OVER_PATH = "/internal/game-over"


def _send(path: str, payload: dict) -> None:
    url, secret = os.environ.get("CHAT_URL", "").rstrip("/"), os.environ.get("WEREWOLF_SECRET", "")
    if not url or len(secret) < servicesig.MIN_SECRET_CHARS:
        return  # not set up: nothing to tell
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{url}{path}", data=body, headers={"Content-Type": "application/json", **servicesig.sign(secret, body, f"POST {path}")}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310 - the address of our own chat
        return


def game_over(app: FastAPI, record) -> bool:
    """Say in the room of the game (if the chat has one) that it is over, with every role and what all of the players saw. Blocking: run it in a thread. True when told."""
    sender = getattr(app.state, "chat_call", None) or _send
    try:
        sender(GAME_OVER_PATH, {
            "code": record.room_code, "winner": record.winner, "days": record.days, "size": record.size,
            "roles": list(record.roles), "seen": list(record.seen),
        })
        return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        log.warning("The chat could not be told that the game %s is over", record.room_code, exc_info=True)
        return False
