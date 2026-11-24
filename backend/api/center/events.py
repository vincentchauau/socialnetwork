"""Account events: the outbox in `account_events` and the relay that publishes it to a Redis Stream.

An event row is written in the SAME transaction as the change it describes (account deletion, rename), so a
rolled back change leaves no event and a committed one can never be lost. The relay then copies unpublished
rows, in id order, to the stream `sn:events:account` (XADD, MAXLEN ~10000) and sets `published_at`.

Guarantees: AT LEAST ONCE. A crash between XADD and the `published_at` update publishes that row again, so
consumers (see sn_shared.events) must be idempotent. Order is the outbox id order (rows are locked while being
relayed, so replicas do not interleave). Without REDIS_URL the relay does nothing and rows stay in the table
(they are kept, not purged, until a Redis is configured and they are published). Published rows are purged
after 7 days.
"""

import json
import logging
import threading
import time
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from api.center.models import AccountEvent, utcnow
from sn_shared.events import ACCOUNT_STREAM

log = logging.getLogger("sn.events")

USER_DELETED = "user.deleted"
USER_RENAMED = "user.renamed"
STREAM_MAXLEN = 10_000
BATCH_SIZE = 100
RELAY_INTERVAL_SECONDS = 2.0
PUBLISHED_KEEP = timedelta(days=7)
PURGE_INTERVAL_SECONDS = 3600.0
WARN_INTERVAL_SECONDS = 60.0
REDIS_TIMEOUT_SECONDS = 2.0


def add_event(
    db: Session, event_type: str, user_id: int, payload: dict[str, Any], *, with_seq: bool = False
) -> AccountEvent:
    """Stage an outbox row in the caller's transaction (the caller commits).

    `with_seq` adds `seq` (= the row id, monotonic) to the payload so consumers can drop stale events.
    """
    event = AccountEvent(type=event_type, user_id=user_id, payload=json.dumps(payload, separators=(",", ":")))
    db.add(event)
    if with_seq:
        db.flush()  # assigns the id
        event.payload = json.dumps({**payload, "seq": event.id}, separators=(",", ":"))
    return event


def stream_fields(event: AccountEvent) -> dict[str, str]:
    return {"event_id": str(event.id), "type": event.type, "user_id": str(event.user_id), "payload": event.payload}


def redis_client_factory(redis_url: str) -> Callable[[], Any] | None:
    """A lazy factory for the relay's client (None without a URL)."""
    if not redis_url:
        return None

    def make() -> Any:
        import redis

        return redis.Redis.from_url(
            redis_url, socket_timeout=REDIS_TIMEOUT_SECONDS, socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            decode_responses=True,
        )

    return make


class EventRelay:
    def __init__(
        self, session_factory: sessionmaker, client_factory: Callable[[], Any] | None, *,
        interval: float = RELAY_INTERVAL_SECONDS,
    ) -> None:  # fmt: skip
        self._sessions = session_factory
        self._client_factory = client_factory
        self._client: Any = None
        self._interval = interval
        self._lock = threading.Lock()  # one publisher per process at a time
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_warned: float | None = None
        self._last_purge: float | None = None

    @property
    def enabled(self) -> bool:
        return self._client_factory is not None

    def _warn(self, exc: Exception) -> None:
        now = time.monotonic()
        if self._last_warned is None or now - self._last_warned >= WARN_INTERVAL_SECONDS:
            self._last_warned = now
            log.warning("account events not published (%s): will retry", type(exc).__name__)

    def publish_pending(self) -> int:
        """Publish unpublished rows in id order; returns how many. Never raises (failures retry later)."""
        if self._client_factory is None:
            return 0
        with self._lock:
            try:
                if self._client is None:
                    self._client = self._client_factory()
                published = self._publish_batches(self._client)
                self._purge_if_due()
                return published
            except Exception as exc:  # noqa: BLE001 - Redis or DB trouble must not kill the relay thread
                self._warn(exc)
                return 0

    def _publish_batches(self, client: Any) -> int:
        total = 0
        while True:
            with self._sessions() as db:
                rows = list(
                    db.scalars(
                        select(AccountEvent)
                        .where(AccountEvent.published_at.is_(None))
                        .order_by(AccountEvent.id)
                        .limit(BATCH_SIZE)
                        .with_for_update()  # replicas wait for each other: no interleaved order
                    )
                )
                for event in rows:  # a failure stops here: rows already marked are committed below
                    try:
                        client.xadd(ACCOUNT_STREAM, stream_fields(event), maxlen=STREAM_MAXLEN, approximate=True)
                    except Exception:
                        db.commit()
                        raise
                    event.published_at = utcnow()
                db.commit()
            total += len(rows)
            if len(rows) < BATCH_SIZE:
                return total

    def _purge_if_due(self) -> None:
        now = time.monotonic()
        if self._last_purge is not None and now - self._last_purge < PURGE_INTERVAL_SECONDS:
            return
        self._last_purge = now
        with self._sessions() as db:
            db.execute(
                delete(AccountEvent)
                .where(AccountEvent.published_at < utcnow() - PUBLISHED_KEEP)
                .execution_options(synchronize_session=False)
            )
            db.commit()

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="account-event-relay", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.publish_pending()
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
