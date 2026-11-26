"""QR sign-in state machine: pending -> approved -> consumed (or denied / expired). Every transition is a
conditional UPDATE, so two racing requests can never both win."""

import hmac
import secrets
import time
from datetime import datetime, timedelta

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from api.center.models import QrLogin, utcnow
from sn_shared.tokens import hash_token

import logging
logger = logging.getLogger(__name__)

TTL_SECONDS = 120
ID_BYTES = 16  # 32 hex characters
POLL_TOKEN_BYTES = 32
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O, 1/I/L
CODE_LENGTH = 4
MAX_WRONG_CODES = 3
PURGE_AFTER = timedelta(hours=1)
UA_MAX = 200
IP_MAX = 64


def new_code() -> str:
    try:
        return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("new_code failed")
        raise


def token_matches(row: QrLogin, token: str) -> bool:
    try:
        return hmac.compare_digest(row.poll_hash, hash_token(token))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("token_matches failed")
        raise


def normalise_code(code: str) -> str:
    try:
        return code.strip().upper()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("normalise_code failed")
        raise


def purge(db: Session) -> None:
    """Rows are useless once expired; opportunistic, on start."""
    try:
        db.execute(delete(QrLogin).where(QrLogin.expires_at < utcnow() - PURGE_AFTER).execution_options(synchronize_session=False))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("purge failed")
        raise


PURGE_EVERY_SECONDS = 60.0
last_purge = 0.0


def maybe_purge(db: Session) -> None:
    """purge() at most once a minute per process (called from poll/approve)."""
    try:
        global last_purge
        now = time.monotonic()
        if now - last_purge >= PURGE_EVERY_SECONDS:
            last_purge = now
            purge(db)
            db.commit()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("maybe_purge failed")
        raise


def create(db: Session, *, ip: str, user_agent: str, requester_sid: str | None) -> tuple[QrLogin, str]:
    try:
        purge(db)
        token = secrets.token_urlsafe(POLL_TOKEN_BYTES)
        now = utcnow()
        row = QrLogin(
            id=secrets.token_bytes(ID_BYTES).hex(), poll_hash=hash_token(token), verify_code=new_code(), status="pending",
            requester_ip=ip[:IP_MAX], requester_user_agent=user_agent[:UA_MAX], requester_sid=requester_sid,
            created_at=now, expires_at=now + timedelta(seconds=TTL_SECONDS),
        )  # fmt: skip
        db.add(row)
        db.commit()
        return row, token
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create failed")
        raise


def is_expired(row: QrLogin, now: datetime | None = None) -> bool:
    try:
        from api.center.usersessions import as_utc

        return as_utc(row.expires_at) <= (now or utcnow())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("is_expired failed")
        raise


def seconds_left(row: QrLogin) -> int:
    try:
        from api.center.usersessions import as_utc

        return max(0, int((as_utc(row.expires_at) - utcnow()).total_seconds()))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("seconds_left failed")
        raise


def transition_qr(db: Session, request_id: str, from_status: str, **values) -> bool:
    """pending/approved -> new status, only while unexpired; True when THIS call made the change."""
    try:
        result = db.execute(
            update(QrLogin)
            .where(QrLogin.id == request_id, QrLogin.status == from_status, QrLogin.expires_at > utcnow())
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return result.rowcount == 1
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("transition_qr failed")
        raise


def approve(db: Session, request_id: str, user_id: int, approver_sid: str | None) -> bool:
    try:
        return transition_qr(
            db, request_id, "pending", status="approved", user_id=user_id, approver_sid=approver_sid, approved_at=utcnow()
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("approve failed")
        raise


def deny(db: Session, request_id: str) -> bool:
    try:
        return transition_qr(db, request_id, "pending", status="denied")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("deny failed")
        raise


def consume(db: Session, request_id: str) -> bool:
    try:
        return transition_qr(db, request_id, "approved", status="consumed")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("consume failed")
        raise


def take_attempt(db: Session, request_id: str) -> bool:
    """Spend one of the MAX_WRONG_CODES tries BEFORE the code is compared (atomic): parallel approvals cannot
    all compare before the last failure lands. False when the request is not pending or has no tries left."""
    try:
        result = db.execute(
            update(QrLogin)
            .where(QrLogin.id == request_id, QrLogin.status == "pending", QrLogin.attempts < MAX_WRONG_CODES)
            .values(attempts=QrLogin.attempts + 1)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return result.rowcount == 1
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("take_attempt failed")
        raise


def fail_attempt(db: Session, request_id: str) -> None:
    """After a wrong code: the request is denied once every try is spent."""
    try:
        db.execute(
            update(QrLogin)
            .where(QrLogin.id == request_id, QrLogin.status == "pending", QrLogin.attempts >= MAX_WRONG_CODES)
            .values(status="denied")
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("fail_attempt failed")
        raise
