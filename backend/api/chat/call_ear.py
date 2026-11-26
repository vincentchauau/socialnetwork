"""The chat tells the ear of the calls (the service `callear`) to listen to a call, with a signed call (`sn_shared.servicesig`, the secret `CALLEAR_SECRET`).

The ear joins the LiveKit room as a hidden listener and sends back, one by one, what each person says (`/internal/call-heard`). Without the address and the
secret nothing is listened to: the call is for the people only (and the voice button of the room still works).
"""

import json
import logging
import os
import threading
import urllib.error
import urllib.request

from sn_shared import servicesig

logger = logging.getLogger(__name__)

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
DEFAULT_URL = "http://callear:8200"


def settings() -> tuple[str, str] | None:
    try:
        url, secret = os.environ.get("CALLEAR_URL", "").strip().rstrip("/") or DEFAULT_URL, os.environ.get("CALLEAR_SECRET", "")
        return (url, secret) if len(secret) >= servicesig.MIN_SECRET_CHARS else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("settings failed")
        raise


def watch(room_name: str, slug: str) -> bool:
    """Ask the ear to listen to this LiveKit room (blocking: run it in a thread). It is only asked again, never harmed, when it already does. True when told."""
    found = settings()
    if found is None:
        return False
    url, secret = found
    body = json.dumps({"room": room_name, "slug": slug}).encode()
    request = urllib.request.Request(f"{url}/watch", data=body, headers={"Content-Type": "application/json", **servicesig.sign(secret, body, "POST /watch")}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310 - the address of our own service
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        log.warning("the ear of the calls could not be told to listen to %s", slug, exc_info=True)
        return False


def watch_in_background(room_name: str, slug: str) -> None:
    try:
        threading.Thread(target=watch, args=(room_name, slug), daemon=True).start()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("watch_in_background failed")
        raise
