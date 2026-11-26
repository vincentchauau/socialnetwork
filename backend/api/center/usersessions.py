"""The `user_sessions` table: one row per signed-in device, revocable at once (here and in every other app).

A token carries its row's `sid`. Tokens issued before this release have no `sid`: they stay valid until they
expire (the legacy window) and cannot be listed or revoked one by one; a refresh upgrades them to a row.
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from api.center.audit import audit
from api.center.config import Settings
from api.center.models import UserSession, utcnow
from sn_shared import revocation

import logging
logger = logging.getLogger(__name__)

SID_BYTES = 16  # 32 hex characters
USER_AGENT_MAX = 200
IP_MAX = 64
TOUCH_INTERVAL_SECONDS = 60
METHODS = ("password", "google", "email", "phone", "passkey", "voice", "webcam", "qr", "refresh")
DEFAULT_METHOD = "password"
MAX_LIVE_SESSIONS = 50  # per user: the oldest are revoked beyond this
REVOKED_KEEP_DAYS = 1
REVOCATION_SLACK_SECONDS = 60  # published keys outlive the longest access token by this much


def request_ip(request: Request) -> str:
    try:
        return request.client.host if request.client else "unknown"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("request_ip failed")
        raise


def as_utc(value: datetime) -> datetime:
    """SQLite hands timestamps back naive; they are always UTC."""
    try:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("as_utc failed")
        raise


def checked_method(method: str | None) -> str:
    try:
        return method if method in METHODS else DEFAULT_METHOD
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("checked_method failed")
        raise


def purge_stale(db: Session, refresh_days: int) -> None:
    """Rows idle for longer than a refresh token lives, and rows revoked over a day ago, can never matter again
    (a revoked sid whose row is gone is rejected just the same). Opportunistic, on sign-in."""
    try:
        now = utcnow()
        db.execute(
            delete(UserSession)
            .where(
                or_(
                    UserSession.last_seen_at < now - timedelta(days=refresh_days),
                    UserSession.revoked_at < now - timedelta(days=REVOKED_KEEP_DAYS),
                )
            )
            .execution_options(synchronize_session=False)
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("purge_stale failed")
        raise


def create(db: Session, request: Request, user_id: int, method: str, settings: Settings) -> str:
    """Insert a row for a new sign-in (purging stale rows, revoking the oldest beyond the cap) and return its sid.
    Commits."""
    try:
        purge_stale(db, settings.refresh_days)
        now = utcnow()
        sid = secrets.token_bytes(SID_BYTES).hex()
        db.add(
            UserSession(
                sid=sid, user_id=user_id, created_at=now, last_seen_at=now, ip=request_ip(request)[:IP_MAX],
                user_agent=request.headers.get("user-agent", "")[:USER_AGENT_MAX], method=checked_method(method),
            )
        )
        db.commit()
        live = active_sessions(db, user_id)  # newest first
        if len(live) > MAX_LIVE_SESSIONS:
            revoke(db, live[MAX_LIVE_SESSIONS:], settings.access_minutes * 60 + REVOCATION_SLACK_SECONDS)
        return sid
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create failed")
        raise


def live_session(db: Session, sid: str, user_id: int) -> UserSession | None:
    """The row when it belongs to the user and is not revoked."""
    try:
        row = db.get(UserSession, sid)
        if row is None or row.user_id != user_id or row.revoked_at is not None:
            return None
        return row
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("live_session failed")
        raise


def touch(db: Session, row: UserSession) -> None:
    """Update last_seen_at at most once per TOUCH_INTERVAL_SECONDS (a conditional UPDATE, so cheap and race-safe)."""
    try:
        now = utcnow()
        if (now - as_utc(row.last_seen_at)).total_seconds() < TOUCH_INTERVAL_SECONDS:
            return
        db.execute(
            update(UserSession)
            .where(
                UserSession.sid == row.sid,
                UserSession.last_seen_at < now - timedelta(seconds=TOUCH_INTERVAL_SECONDS),
            )
            .values(last_seen_at=now)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        row.last_seen_at = now
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("touch failed")
        raise


def active_sessions(db: Session, user_id: int) -> list[UserSession]:
    try:
        return list(
            db.scalars(
                select(UserSession)
                .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                .order_by(UserSession.created_at.desc(), UserSession.sid)
            )
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("active_sessions failed")
        raise


def revoke(db: Session, rows: list[UserSession], ttl_seconds: int) -> int:
    """Mark rows revoked (committed), then publish each sid to the cross-app store; returns how many."""
    try:
        now = utcnow()
        for row in rows:
            row.revoked_at = now
        db.commit()
        failed = sum(1 for row in rows if not revocation.publish_session_revoked(row.sid, ttl_seconds))
        if failed and revocation.configured():
            audit.warning("revocation not published for %d of %d sessions: other apps may accept them until expiry",
                          failed, len(rows))  # fmt: skip
        return len(rows)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("revoke failed")
        raise


def revoke_all_of(db: Session, user_id: int, keep_sid: str | None = None) -> None:
    """Part of a token_version bump (the caller commits and publishes the new minimum version)."""
    try:
        query = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        if keep_sid is not None:
            query = query.where(UserSession.sid != keep_sid)
        db.execute(query.values(revoked_at=utcnow()).execution_options(synchronize_session=False))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("revoke_all_of failed")
        raise
