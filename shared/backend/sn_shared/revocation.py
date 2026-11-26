"""Immediate revocation of access tokens across every app, through an optional Redis.

Apps verify the HS256 JWT locally, so on its own a token lives until it expires. `center` therefore publishes
two kinds of key (both with a TTL of the access-token lifetime + 60 s, so nothing outlives the tokens it blocks):

- `sn:revoked:sid:<sid>`  (value 1)    a single session (device) was revoked;
- `sn:minver:<user_id>`   (value N)    the account's latest `token_version`: tokens with `ver < N` are dead.

Every app then rejects such a token in `get_current_user` (one MGET per request).

Trade-offs (deliberate):
- No `REDIS_URL`, or the `redis` package missing: every check is a no-op and publishing does nothing.
- Redis errors or timeouts (0.3 s socket timeout) FAIL OPEN: the request is accepted and a rate-limited line is
  logged. Availability wins over a revocation that is at most one access-token lifetime (60 min by default) late;
  `center` itself checks the database on every request and refresh, so the window only exists in the other apps.
"""

import logging
import os
import threading
import time
from typing import Any

log = logging.getLogger("sn.revocation")

SOCKET_TIMEOUT_SECONDS = 0.3
SID_PREFIX = "sn:revoked:sid:"
MINVER_PREFIX = "sn:minver:"
ERROR_LOG_INTERVAL_SECONDS = 60.0
MAX_WATCH_RETRIES = 5

_UNSET: Any = object()
revocation_lock = threading.RLock()
_override: Any = _UNSET  # tests: a client (or None to disable) that replaces the REDIS_URL one
_cached: tuple[str, Any] | None = None  # (url, client)
_last_logged: float | None = None


def use_client(client: Any) -> None:
    """Use `client` (any redis-py compatible object, or None to disable); `reset()` goes back to REDIS_URL."""
    global _override
    _override = client


def reset() -> None:
    global _override, _cached, _last_logged
    _override, _cached, _last_logged = _UNSET, None, None


def log_failure(action: str, exc: BaseException) -> None:
    """One line per minute at most, so an outage cannot flood the logs."""
    global _last_logged
    with revocation_lock:
        now = time.monotonic()
        if _last_logged is not None and now - _last_logged < ERROR_LOG_INTERVAL_SECONDS:
            return
        _last_logged = now
    log.error("revocation store unavailable (%s during %s): failing open", type(exc).__name__, action)


def client_revocation() -> Any:
    global _cached
    if _override is not _UNSET:
        return _override
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    with revocation_lock:
        if _cached is not None and _cached[0] == url:
            return _cached[1]
        try:
            import redis  # lazily: an app without the package still works, just without revocation
        except ImportError as exc:
            log_failure("import", exc)
            return None
        client = redis.Redis.from_url(
            url, socket_timeout=SOCKET_TIMEOUT_SECONDS, socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
            decode_responses=True,
        )
        _cached = (url, client)
        return client


def configured() -> bool:
    """True when a store is set up (so a failed publish is worth a warning)."""
    return client_revocation() is not None


def is_revoked(user_id: int, sid: str | None, ver: int | None) -> bool:
    """True when the session was revoked or the token version is below the account's published minimum."""
    client = client_revocation()
    if client is None:
        return False
    keys = ([f"{SID_PREFIX}{sid}"] if sid else []) + ([f"{MINVER_PREFIX}{user_id}"] if ver is not None else [])
    if not keys:
        return False
    try:
        values = client.mget(keys)
    except Exception as exc:  # noqa: BLE001 - any store failure must never take the app down
        log_failure("check", exc)
        return False
    if sid and values[0] is not None:
        return True
    if ver is not None and values[-1] is not None:
        try:
            return int(values[-1]) > ver
        except (TypeError, ValueError):
            return True  # a corrupt minimum is never read as "fine"
    return False


def publish_session_revoked(sid: str, ttl_seconds: int) -> bool:
    client = client_revocation()
    if client is None:
        return False
    try:
        client.set(f"{SID_PREFIX}{sid}", 1, ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        log_failure("publish", exc)
        return False
    return True


def watch_error():
    from redis.exceptions import WatchError

    return WatchError


def publish_min_version(user_id: int, ver: int, ttl_seconds: int) -> bool:
    """Record `ver` as the account's minimum token version (never lowers an existing value)."""
    client = client_revocation()
    if client is None:
        return False
    key = f"{MINVER_PREFIX}{user_id}"
    try:
        for _ in range(MAX_WATCH_RETRIES):  # WATCH/MULTI: the stored value only ever goes up, even with two writers
            with client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    current = pipe.get(key)
                    try:
                        higher = current is None or int(current) < ver
                    except ValueError:
                        higher = True  # overwrite a corrupt value
                    if not higher:
                        return True
                    pipe.multi()
                    pipe.set(key, ver, ex=ttl_seconds)
                    pipe.execute()
                    return True
                except watch_error():
                    continue
        return False
    except Exception as exc:  # noqa: BLE001
        log_failure("publish", exc)
        return False
