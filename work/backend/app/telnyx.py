"""Telnyx voice experiments: a verified webhook (public route) and an admin-only list of masked call events.

The webhook is reachable without the auth cookie, so it trusts nothing but the Ed25519 signature Telnyx puts on
every request (`telnyx-signature-ed25519` over `<timestamp>|<raw body>`, `telnyx-timestamp`). Secrets come from
the environment only (TELNYX_PUBLIC_KEY, TELNYX_API_KEY) and are never logged; Telnyx responses are not logged.
The media-stream WebSocket receiver and outbound SMS of the original experiment are deliberately not ported.
"""

import base64
import binascii
import json
import logging
import os
import re
import time
from typing import Annotated
from urllib.parse import quote

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CallEvent
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO line prints the request URL

router = APIRouter()

API_BASE = "https://api.telnyx.com/v2/calls"
MAX_AGE_SECONDS = 300
MAX_BODY_BYTES = 256 * 1024
API_TIMEOUT_SECONDS = 5.0
MAX_STORED_EVENTS = 5000
MAX_GREETING_CHARS = 500
HANDLED_EVENTS = ("call.initiated", "call.answered", "call.recording.saved")
DEFAULT_GREETING = "Xin chào, đây là đường dây thử nghiệm. Vui lòng để lại lời nhắn sau tiếng bíp."
CALL_CONTROL_ID = re.compile(r"[A-Za-z0-9_:=.\-]{1,200}\Z")
UNCONFIGURED = "Webhook Telnyx chưa được cấu hình"


def mask_number(value: object) -> str:
    """All but the last 2 digits become '*' (digits only; anything else is dropped)."""
    digits = re.sub(r"\D", "", value) if isinstance(value, str) else ""
    digits = digits[-20:]
    return "*" * max(len(digits) - 2, 0) + digits[-2:] if len(digits) > 2 else "*" * len(digits)


def public_key() -> Ed25519PublicKey | None:
    raw = os.environ.get("TELNYX_PUBLIC_KEY", "").strip()
    if not raw:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(raw, validate=True))
    except (ValueError, binascii.Error):
        logger.error("TELNYX_PUBLIC_KEY is set but is not a base64 Ed25519 public key")
        return None


def signature_is_valid(key: Ed25519PublicKey, body: bytes, signature: str, timestamp: str, now: float) -> bool:
    if not timestamp.isdigit() or abs(now - int(timestamp)) > MAX_AGE_SECONDS:
        return False
    try:
        key.verify(base64.b64decode(signature, validate=True), timestamp.encode() + b"|" + body)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


async def verified_body(
    request: Request,
    signature: Annotated[str | None, Header(alias="telnyx-signature-ed25519")] = None,
    timestamp: Annotated[str | None, Header(alias="telnyx-timestamp")] = None,
) -> bytes:
    """The raw body, once the signature is proven (503 when unconfigured, 401 when unsigned or wrong)."""
    key = public_key()
    if key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNCONFIGURED)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(413, "Nội dung quá lớn")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(413, "Nội dung quá lớn")
    if not signature or not timestamp or not signature_is_valid(key, body, signature, timestamp, time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chữ ký không hợp lệ")
    return body


def _post_action(request: Request, call_control_id: str, action: str, payload: dict | None = None) -> None:
    """One Telnyx call-control action; failures are logged by type only (never the key or the response)."""
    api_key = os.environ.get("TELNYX_API_KEY", "").strip()
    if not api_key or not CALL_CONTROL_ID.match(call_control_id):
        return
    url = f"{API_BASE}/{quote(call_control_id, safe='')}/actions/{action}"
    try:
        with httpx.Client(timeout=API_TIMEOUT_SECONDS, transport=request.app.state.telnyx_transport) as client:
            response = client.post(url, json=payload or {}, headers={"Authorization": f"Bearer {api_key}"})
        if response.status_code >= 400:
            logger.warning("telnyx action %s answered HTTP %s", action, response.status_code)
    except httpx.HTTPError as error:
        logger.warning("telnyx action %s failed (%s)", action, type(error).__name__)


def _react(request: Request, event_type: str, call_control_id: str) -> None:
    if event_type == "call.initiated":
        _post_action(request, call_control_id, "answer")
    elif event_type == "call.answered":
        greeting = os.environ.get("TELNYX_GREETING", "").strip()[:MAX_GREETING_CHARS] or DEFAULT_GREETING
        _post_action(
            request, call_control_id, "speak", {"payload": greeting, "voice": "female", "language": "vi-VN"}
        )
        _post_action(request, call_control_id, "record_start", {"format": "mp3", "channels": "single"})


def _trim_old(db: Session) -> None:
    old = db.scalars(select(CallEvent.id).order_by(CallEvent.id.desc()).offset(MAX_STORED_EVENTS)).all()
    if old:
        db.execute(delete(CallEvent).where(CallEvent.id.in_(old)))


def _text(value: object, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ""


@router.post("/telnyx/webhook")
def webhook(request: Request, body: bytes = Depends(verified_body), db: Session = Depends(get_db)) -> dict:
    try:
        data = json.loads(body).get("data")
        event_id = data["id"]
        event_type = data["event_type"]
    except (ValueError, AttributeError, KeyError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sự kiện không hợp lệ") from None
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 100 or not isinstance(event_type, str):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sự kiện không hợp lệ")
    if event_type not in HANDLED_EVENTS:
        return {"status": "ignored"}
    payload = data.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    call_control_id = _text(payload.get("call_control_id"), 200)
    if db.scalar(select(CallEvent.id).where(CallEvent.telnyx_event_id == event_id)) is not None:
        return {"status": "duplicate"}
    db.add(
        CallEvent(
            telnyx_event_id=event_id,
            event_type=event_type,
            call_control_id=call_control_id,
            from_number_masked=mask_number(payload.get("from")),
            to_number_masked=mask_number(payload.get("to")),
            payload_size=len(body),
        )
    )
    try:
        db.flush()
        _trim_old(db)
        db.commit()
    except IntegrityError:  # a concurrent delivery of the same event won the race
        db.rollback()
        return {"status": "duplicate"}
    _react(request, event_type, call_control_id)
    return {"status": "ok"}


def _event_out(row: CallEvent) -> dict:
    return {
        "id": row.id,
        "eventType": row.event_type,
        "callControlId": row.call_control_id,
        "from": row.from_number_masked,
        "to": row.to_number_masked,
        "payloadSize": row.payload_size,
        "createdAt": row.created_at.isoformat(),
    }


@router.get("/calls")
def list_calls(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị viên được xem danh sách cuộc gọi")
    rows = db.scalars(select(CallEvent).order_by(CallEvent.id.desc()).limit(limit))
    return [_event_out(row) for row in rows]
