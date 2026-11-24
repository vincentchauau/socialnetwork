"""Tickets to a LiveKit room, and closing a room (LiveKit is the video of the calls: shared/infra, service `livekit`).

A ticket is a JWT (HS256) signed with `LIVEKIT_API_SECRET` for the key `LIVEKIT_API_KEY`: whoever holds it may join one room as one person, for a
while. The chat gives it to the members of a room only. Without the key and the secret there are no calls (`configured()` is false).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TICKET_SECONDS = 2 * 60 * 60  # long enough for a meeting; one who is sent away loses the room at once (see `close_room`)
ADMIN_SECONDS = 60
TIMEOUT_SECONDS = 5
DEFAULT_URL = "ws://localhost:7880"
DEFAULT_HTTP = "http://livekit:7880"
MIN_SECRET_CHARS = 16


def _settings() -> tuple[str, str] | None:
    key, secret = os.environ.get("LIVEKIT_API_KEY", ""), os.environ.get("LIVEKIT_API_SECRET", "")
    return (key, secret) if key and len(secret) >= MIN_SECRET_CHARS else None


def configured() -> bool:
    return _settings() is not None


def server_url() -> str:
    """Where the browsers reach LiveKit."""
    return os.environ.get("LIVEKIT_URL", "").strip().rstrip("/") or DEFAULT_URL


def _b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _sign(claims: dict) -> str:
    found = _settings()
    if found is None:
        raise RuntimeError("LiveKit is not set up")
    key, secret = found
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"iss": key, **claims}).encode())
    signature = _b64(hmac.new(secret.encode(), head + b"." + body, hashlib.sha256).digest())
    return (head + b"." + body + b"." + signature).decode()


def ticket(identity: str, name: str, room: str, now: float | None = None) -> str:
    """The ticket for this person to join this room: they may publish (microphone, camera, screen) and listen."""
    moment = int(now if now is not None else time.time())
    return _sign({
        "sub": identity, "name": name, "nbf": moment - 5, "exp": moment + TICKET_SECONDS,
        "video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True},
    })


def _admin(room: str, now: float | None = None) -> str:
    moment = int(now if now is not None else time.time())
    return _sign({"sub": "chat", "nbf": moment - 5, "exp": moment + ADMIN_SECONDS, "video": {"roomAdmin": True, "room": room}})


def close_room(room: str) -> bool:
    """Send everybody out of the room and drop it (blocking: run it in a thread). A room that is not there is not an error. True when done."""
    if not configured():
        return False
    base = os.environ.get("LIVEKIT_HTTP", "").strip().rstrip("/") or DEFAULT_HTTP
    request = urllib.request.Request(
        f"{base}/twirp/livekit.RoomService/DeleteRoom", data=json.dumps({"room": room}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_admin(room)}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310 - the address of our own LiveKit
            return True
    except urllib.error.HTTPError as caught:
        return caught.code == 404  # no such room: nobody is in it
    except (urllib.error.URLError, TimeoutError, OSError):
        log.warning("the room %s could not be closed at LiveKit", room, exc_info=True)
        return False
