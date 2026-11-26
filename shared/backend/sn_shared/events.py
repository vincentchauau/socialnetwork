"""Consume account events (`user.deleted`, `user.renamed`) published by center to a Redis Stream.

Center writes the events to the stream `sn:events:account`. Every app runs one consumer group named after
itself, so each app sees every event once (per group) and a NEW app catches up on the retained history
(the group is created at id 0). Wiring, in an app's lifespan:

    handle = sn_shared.events.start_account_consumer("chat", SessionLocal)
    ...
    handle.stop()

The app implements the module `app/account_events.py` (looked up as `app.account_events`):

    def on_user_deleted(db: Session, user_id: int) -> None: ...
    def on_user_renamed(db: Session, user_id: int, new_username: str) -> None: ...
    def on_user_created(db: Session, user_id: int, username: str, kind: str, body: dict) -> None: ...   # optional

Handlers get a fresh session and the consumer commits it. DELIVERY IS AT LEAST ONCE, so handlers MUST be
idempotent (deleting rows of a user twice, or setting a username to the same value, must be harmless) and must
tolerate events for users the app has never seen. A handler exception rolls back and leaves the message
pending: it is retried after it has been idle for 60 s, and after 5 deliveries it is moved to the dead-letter
stream `sn:events:account:dead` (fields of the original + `app`, `error` = exception class name, `original_id`)
and acknowledged. A missing module/handler is a skip with a warning (acknowledged, so the stream never stalls).

A `user.renamed` event may carry `seq` (monotonic); the consumer keeps a per-user high-water mark in Redis
(`sn:events:rename-seq:<app>:<user_id>`, 30 days) and skips, with an ack, a rename whose seq is not newer
than the mark, so a late redelivery can never overwrite a newer name. Events without `seq` are always handled.

Without a Redis URL (argument or REDIS_URL) or without the `redis` package everything here is a no-op.
"""

import importlib
import inspect
import json
import logging
import os
import secrets
import socket
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

log = logging.getLogger("sn.events")

ACCOUNT_STREAM = "sn:events:account"
DEAD_STREAM = "sn:events:account:dead"
USER_DELETED = "user.deleted"
USER_RENAMED = "user.renamed"
USER_CREATED = "user.created"  # only for accounts made by the platform (virtual people): a person who signs up is met on first use
HANDLERS_MODULE = "app.account_events"
MAX_DELIVERIES = 5
RECLAIM_IDLE_MS = 60_000
DEAD_MAXLEN = 10_000
BATCH = 50
SOCKET_TIMEOUT_SECONDS = 5.0
WARN_INTERVAL_SECONDS = 60.0
SEQ_KEY = "sn:events:rename-seq:{app}:{user_id}"
SEQ_TTL_SECONDS = 30 * 86400
SEQ_WATCH_RETRIES = 5


class Skip(Exception):
    """Acknowledge without handling (nothing to run, or nothing a retry could fix)."""


class NoopHandle:
    def stop(self) -> None:
        try:
            return None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("stop failed")
            raise


class AccountConsumer:
    """One consumer group member. `process_once()` does one claim+read round (the thread just loops on it)."""

    def __init__(
        self, app_name: str, session_factory: Callable[[], Any], client: Any, *, poll_ms: int = 2000,
        reclaim_idle_ms: int = RECLAIM_IDLE_MS, handlers_module: str = HANDLERS_MODULE,
    ) -> None:  # fmt: skip
        try:
            self.group = app_name
            self.consumer = f"{app_name}-{socket.gethostname()}-{os.getpid()}-{secrets.token_hex(3)}"
            self._sessions = session_factory
            self.client_revocation = client
            self._poll_ms = poll_ms
            self._reclaim_idle_ms = reclaim_idle_ms
            self._module_name = handlers_module
            self._module: Any = None
            self._warned_module = False
            self._last_warned: float | None = None
            self._stop = threading.Event()
            self._thread: threading.Thread | None = None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise

    # --- stream plumbing -----------------------------------------------------------------------

    def ensure_group(self) -> None:
        import redis

        try:
            self.client_revocation.xgroup_create(ACCOUNT_STREAM, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def process_once(self, block_ms: int = 0) -> int:
        """Handle reclaimed stale entries, then new ones; returns how many messages were looked at."""
        try:
            handled = 0
            claimed = self.client_revocation.xautoclaim(
                ACCOUNT_STREAM, self.group, self.consumer, min_idle_time=self._reclaim_idle_ms, start_id="0-0",
                count=BATCH,
            )[1]
            for message_id, fields in claimed:
                if fields is None:  # trimmed from the stream while pending
                    self.ack_events(message_id)
                else:
                    self.handle_events(message_id, fields)
                handled += 1
            reply = self.client_revocation.xreadgroup(
                self.group, self.consumer, {ACCOUNT_STREAM: ">"}, count=BATCH, block=block_ms or None
            )
            for _stream, messages in reply or []:
                for message_id, fields in messages:
                    self.handle_events(message_id, fields)
                    handled += 1
            return handled
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("process_once failed")
            raise

    def deliveries_events(self, message_id: str) -> int:
        try:
            rows = self.client_revocation.xpending_range(ACCOUNT_STREAM, self.group, min=message_id, max=message_id, count=1)
            return int(rows[0]["times_delivered"]) if rows else 1
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("deliveries_events failed")
            raise

    def ack_events(self, message_id: str) -> None:
        try:
            self.client_revocation.xack(ACCOUNT_STREAM, self.group, message_id)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("ack_events failed")
            raise

    def handle_events(self, message_id: str, fields: dict) -> None:
        try:
            self.dispatch_events(fields)
        except Skip as skip:
            log.warning("account event %s skipped: %s", message_id, skip)
            self.ack_events(message_id)
        except Exception as exc:  # noqa: BLE001 - any handler failure is retried, then dead-lettered
            if self.deliveries_events(message_id) >= MAX_DELIVERIES:
                self.dead_letter(message_id, fields, exc)
            else:
                log.warning("account event %s failed (%s): will be retried", message_id, type(exc).__name__)
        else:
            self.ack_events(message_id)

    def dead_letter(self, message_id: str, fields: dict, exc: Exception) -> None:
        try:
            log.error("account event %s dead-lettered after %d deliveries (%s)", message_id, MAX_DELIVERIES,
                      type(exc).__name__)  # fmt: skip
            self.client_revocation.xadd(
                DEAD_STREAM,
                {**fields, "app": self.group, "error": type(exc).__name__, "original_id": message_id},
                maxlen=DEAD_MAXLEN, approximate=True,
            )  # fmt: skip
            self.ack_events(message_id)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("dead_letter failed")
            raise

    # --- handler dispatch ----------------------------------------------------------------------

    def handlers_events(self) -> Any:
        try:
            if self._module is None:
                try:
                    self._module = importlib.import_module(self._module_name)
                except ModuleNotFoundError as exc:
                    if exc.name and not self._module_name.startswith(exc.name):
                        raise  # the handlers module exists but one of ITS imports is missing: a real failure
                    if not self._warned_module:
                        self._warned_module = True
                        log.warning("%s not found: account events are skipped for %s", self._module_name, self.group)
                    raise Skip(f"no {self._module_name}") from None
            return self._module
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("handlers_events failed")
            raise

    def dispatch_events(self, fields: dict) -> None:
        kind = fields.get("type")
        function_name = {USER_DELETED: "on_user_deleted", USER_RENAMED: "on_user_renamed", USER_CREATED: "on_user_created"}.get(kind)
        try:
            user_id = int(fields["user_id"])
            payload = json.loads(fields.get("payload") or "{}")
        except (KeyError, ValueError, TypeError):
            raise Skip("malformed event") from None
        if function_name is None:
            raise Skip(f"unknown event type {kind!r}")
        handler = getattr(self.handlers_events(), function_name, None)
        if handler is None:
            raise Skip(f"{self._module_name} has no {function_name}")
        args: tuple = (user_id,)
        if kind == USER_CREATED:
            name = payload.get("username") if isinstance(payload, dict) else None
            if not isinstance(name, str) or not name:
                raise Skip("created event without a username")
            args = (user_id, name, str(payload.get("kind") or "human"), payload)  # the whole body: each app takes what it needs
        if kind == USER_RENAMED:
            new_name = payload.get("username") if isinstance(payload, dict) else None
            if not isinstance(new_name, str) or not new_name:
                raise Skip("rename event without a username")
            args = (user_id, new_name)
            seq = payload.get("seq") if isinstance(payload, dict) else None
            seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else None  # legacy events have none
            if seq is not None and seq <= self.rename_mark(user_id):
                raise Skip(f"stale rename of user {user_id} (seq {seq})")
        extra: dict = {}
        wants_name = kind == USER_DELETED and "old_username" in inspect.signature(handler).parameters
        if wants_name and isinstance(payload, dict) and isinstance(payload.get("old_username"), str):
            extra["old_username"] = payload["old_username"]  # the row of `users` is already gone: a handler that needs the name is told it
        with self._sessions() as db:
            try:
                handler(db, *args, **extra)
                db.commit()
            except BaseException:
                db.rollback()
                raise
        if kind == USER_RENAMED and seq is not None:
            self.raise_rename_mark(user_id, seq)

    def mark_key(self, user_id: int) -> str:
        try:
            return SEQ_KEY.format(app=self.group, user_id=user_id)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("mark_key failed")
            raise

    def rename_mark(self, user_id: int) -> int:
        """Highest rename `seq` applied for the user (0: none), so a late older event cannot overwrite a newer name."""
        try:
            raw = self.client_revocation.get(self.mark_key(user_id))
            return int(raw) if raw else 0
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("rename_mark failed")
            raise

    def raise_rename_mark(self, user_id: int, seq: int) -> None:
        try:
            import redis

            key = self.mark_key(user_id)
            for _ in range(SEQ_WATCH_RETRIES):
                with self.client_revocation.pipeline() as pipe:
                    try:
                        pipe.watch(key)
                        current = pipe.get(key)
                        if current and int(current) >= seq:
                            return
                        pipe.multi()
                        pipe.set(key, seq, ex=SEQ_TTL_SECONDS)
                        pipe.execute()
                        return
                    except redis.WatchError:
                        continue
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("raise_rename_mark failed")
            raise

    # --- thread --------------------------------------------------------------------------------

    def warn(self, exc: Exception) -> None:
        try:
            now = time.monotonic()
            if self._last_warned is None or now - self._last_warned >= WARN_INTERVAL_SECONDS:
                self._last_warned = now
                log.warning("account event consumer %s: redis problem (%s), retrying", self.group, type(exc).__name__)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("warn failed")
            raise

    def run_events(self) -> None:
        try:
            import redis

            while not self._stop.is_set():
                try:
                    self.ensure_group()
                    while not self._stop.is_set():
                        self.process_once(self._poll_ms)
                except (redis.RedisError, OSError) as exc:
                    self.warn(exc)
                    self._stop.wait(self._poll_ms / 1000)
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("run_events failed")
            raise

    def start(self) -> "AccountConsumer":
        try:
            self._thread = threading.Thread(target=self.run_events, name=f"account-events-{self.group}", daemon=True)
            self._thread.start()
            return self
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("start failed")
            raise

    def stop(self) -> None:
        try:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=self._poll_ms / 1000 + 5)
                self._thread = None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("stop failed")
            raise


def start_account_consumer(
    app_name: str, session_factory: Callable[[], Any], *, redis_url: str | None = None, poll_ms: int = 2000,
    client: Any = None, handlers_module: str = HANDLERS_MODULE,
) -> Any:  # fmt: skip
    """Start the daemon consumer of `app_name`; returns a handle with `stop()`. A no-op handle without Redis.

    `client` (a redis-py compatible object) replaces the URL; it exists for tests. `handlers_module` is where the handlers are when
    several services live in one process (each has its own module).
    """
    try:
        if client is None:
            url = (redis_url if redis_url is not None else os.environ.get("REDIS_URL", "")).strip()
            if not url:
                return NoopHandle()
            try:
                import redis
            except ImportError:
                log.warning("redis package missing: account events are not consumed")
                return NoopHandle()
            client = redis.Redis.from_url(
                url, socket_timeout=SOCKET_TIMEOUT_SECONDS + poll_ms / 1000, socket_connect_timeout=SOCKET_TIMEOUT_SECONDS,
                decode_responses=True,
            )
        return AccountConsumer(app_name, session_factory, client, poll_ms=poll_ms, handlers_module=handlers_module).start()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("start_account_consumer failed")
        raise
