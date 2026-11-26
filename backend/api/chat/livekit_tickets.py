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

logger = logging.getLogger(__name__)

log = logging.getLogger(__name__)

TICKET_SECONDS = 2 * 60 * 60  # long enough for a meeting; one who is sent away loses the room at once (see `close_room`)
ADMIN_SECONDS = 60
TIMEOUT_SECONDS = 5
DEFAULT_URL = "ws://localhost:7880"
DEFAULT_HTTP = "http://livekit:7880"
MIN_SECRET_CHARS = 16


def settings() -> tuple[str, str] | None:
    try:
        key, secret = os.environ.get("LIVEKIT_API_KEY", ""), os.environ.get("LIVEKIT_API_SECRET", "")
        return (key, secret) if key and len(secret) >= MIN_SECRET_CHARS else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("settings failed")
        raise


def configured() -> bool:
    try:
        return settings() is not None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("configured failed")
        raise


def server_url() -> str:
    """Where the browsers reach LiveKit."""
    try:
        return os.environ.get("LIVEKIT_URL", "").strip().rstrip("/") or DEFAULT_URL
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("server_url failed")
        raise


def b64(data: bytes) -> bytes:
    try:
        return base64.urlsafe_b64encode(data).rstrip(b"=")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("b64 failed")
        raise


def sign(claims: dict) -> str:
    try:
        found = settings()
        if found is None:
            raise RuntimeError("LiveKit is not set up")
        key, secret = found
        head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = b64(json.dumps({"iss": key, **claims}).encode())
        signature = b64(hmac.new(secret.encode(), head + b"." + body, hashlib.sha256).digest())
        return (head + b"." + body + b"." + signature).decode()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("sign failed")
        raise


def ticket(identity: str, name: str, room: str, now: float | None = None) -> str:
    """The ticket for this person to join this room: they may publish (microphone, camera, screen) and listen."""
    try:
        moment = int(now if now is not None else time.time())
        return sign({
            "sub": identity, "name": name, "nbf": moment - 5, "exp": moment + TICKET_SECONDS,
            "video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True},
        })
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ticket failed")
        raise


def admin_livekit_tickets(room: str, now: float | None = None) -> str:
    try:
        moment = int(now if now is not None else time.time())
        return sign({"sub": "chat", "nbf": moment - 5, "exp": moment + ADMIN_SECONDS, "video": {"roomAdmin": True, "room": room}})
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("admin_livekit_tickets failed")
        raise


def close_room(room: str) -> bool:
    """Send everybody out of the room and drop it (blocking: run it in a thread). A room that is not there is not an error. True when done."""
    if not configured():
        return False
    base = os.environ.get("LIVEKIT_HTTP", "").strip().rstrip("/") or DEFAULT_HTTP
    request = urllib.request.Request(
        f"{base}/twirp/livekit.RoomService/DeleteRoom", data=json.dumps({"room": room}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {admin_livekit_tickets(room)}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310 - the address of our own LiveKit
            return True
    except urllib.error.HTTPError as caught:
        return caught.code == 404  # no such room: nobody is in it
    except (urllib.error.URLError, TimeoutError, OSError):
        log.warning("the room %s could not be closed at LiveKit", room, exc_info=True)
        return False
