"""A signature for a call from one service to another (the caller acts for a person who has no token to give).

The body is signed together with a timestamp and the call it is for (`scope`, e.g. "POST /internal/ensure"):
`HMAC-SHA256(secret, "<timestamp>.<scope>.<body>")`, hex, so a signature taken from one call cannot be replayed on another. The receiver refuses a signature
that is wrong, that is older (or newer) than `MAX_SKEW_SECONDS`, or when no secret is set (a service never trusts a call it
cannot check). Headers: `X-Service-Timestamp`, `X-Service-Signature`.
"""

import hashlib
import hmac
import time

TIMESTAMP_HEADER = "X-Service-Timestamp"
SIGNATURE_HEADER = "X-Service-Signature"
MAX_SKEW_SECONDS = 60
MIN_SECRET_CHARS = 16


def _digest(secret: str, timestamp: str, scope: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + scope.encode() + b"." + body, hashlib.sha256).hexdigest()


def sign(secret: str, body: bytes, scope: str, *, now: float | None = None) -> dict[str, str]:
    """The two headers to send with `body`."""
    if len(secret) < MIN_SECRET_CHARS:
        raise ValueError("The service secret is missing or too short")
    timestamp = str(int(now if now is not None else time.time()))
    return {TIMESTAMP_HEADER: timestamp, SIGNATURE_HEADER: _digest(secret, timestamp, scope, body)}


def verify(secret: str, body: bytes, scope: str, timestamp: str | None, signature: str | None, *, now: float | None = None) -> bool:
    """True only for a fresh signature made with `secret` over exactly `body` for exactly this `scope`."""
    if len(secret) < MIN_SECRET_CHARS or not timestamp or not signature:
        return False
    try:
        moment = int(timestamp)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - moment) > MAX_SKEW_SECONDS:
        return False
    return hmac.compare_digest(_digest(secret, timestamp, scope, body), signature)
