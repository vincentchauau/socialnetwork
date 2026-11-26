"""QR sign-in: a new device shows a QR code, a signed-in device approves it (README: anti-phishing notes)."""

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from api.center import qr
from api.center.audit import audit
from api.center.db import get_db
from api.center.deps import AuthSession, biometrics_available, check_origin, client_ip, csrf_session, current_session, settings_of, too_many
from api.center.models import QrLogin, User
from api.center.notify import notify
from api.center.reauth import current_sid
from api.center.schemas import MfaRequired, QrApproveBody, QrInfoOut, QrPollBody, QrPollOut, QrStartOut, QrStatusOut, SessionOut
from api.center.sessions import start_login
from api.center.usersessions import as_utc

router = APIRouter(prefix="/auth/qr", tags=["qr"], dependencies=[Depends(check_origin)])

NOT_FOUND = "QR request not found or expired"
BAD_POLL = "Invalid QR request"
WRONG_CODE = "The code does not match the one shown on the new device"
QR_PATH = "/login/qr"


def open_request(db: Session, request_id: str) -> QrLogin:
    """A pending, unexpired request, or 404 (the same answer for every other state)."""
    row = db.get(QrLogin, request_id)
    if row is None or row.status != "pending" or qr.is_expired(row):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return row


@router.post("/start", response_model=QrStartOut, status_code=status.HTTP_201_CREATED)
def start(request: Request, db: Session = Depends(get_db)) -> QrStartOut:
    if not request.app.state.qr_start_throttle.check_and_record(client_ip(request)):
        raise too_many()
    row, token = qr.create(
        db, ip=client_ip(request), user_agent=request.headers.get("user-agent", ""), requester_sid=current_sid(request)
    )
    audit.info("qr start ip=%s", row.requester_ip)
    # The secret (request id) travels in the URL fragment only; the poll token never leaves this browser.
    return QrStartOut(
        request_id=row.id, poll_token=token, verify_code=row.verify_code, expires_in=qr.TTL_SECONDS,
        qr_url=f"{settings_of(request).public_url}{QR_PATH}#r={row.id}",
    )  # fmt: skip


@router.post("/poll", response_model=SessionOut | MfaRequired | QrPollOut)
def poll(body: QrPollBody, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    qr.maybe_purge(db)
    if not request.app.state.qr_poll_throttle.check_and_record(ip):
        raise too_many()
    row = db.get(QrLogin, body.request_id)
    if row is None or not qr.token_matches(row, body.poll_token) or row.status == "consumed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, BAD_POLL)
    if row.status == "denied":
        return QrPollOut(status="denied")
    if qr.is_expired(row) or row.status == "expired":
        return QrPollOut(status="expired")
    if row.status != "approved":
        return QrPollOut(status="pending")
    if not qr.consume(db, row.id):  # lost a race, or expired in the meantime: nothing is issued
        raise HTTPException(status.HTTP_404_NOT_FOUND, BAD_POLL)
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, BAD_POLL)
    result = start_login(
        response, user, settings_of(request), biometrics_available(request), request=request, db=db, method="qr"
    )
    audit.info("qr login %s user=%r ip=%s", "mfa-pending" if isinstance(result, MfaRequired) else "ok", user.username, ip)
    return result


@router.get("/{request_id}", response_model=QrInfoOut)
def info(request_id: str, session: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> QrInfoOut:
    row = open_request(db, request_id)
    return QrInfoOut(
        requester_ip=row.requester_ip, requester_user_agent=row.requester_user_agent,
        created_at=as_utc(row.created_at), expires_in=qr.seconds_left(row),
    )  # fmt: skip


@router.post("/{request_id}/approve", response_model=QrStatusOut)
def approve(
    request_id: str, body: QrApproveBody, request: Request, background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db),
) -> QrStatusOut:  # fmt: skip
    qr.maybe_purge(db)
    row = open_request(db, request_id)
    if session.sid is not None and row.requester_sid == session.sid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This browser cannot approve its own request")
    if not qr.take_attempt(db, request_id):  # counted before comparing: parallel guesses cannot outrun the limit
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if not hmac.compare_digest(qr.normalise_code(body.verify_code), row.verify_code):
        qr.fail_attempt(db, request_id)
        audit.warning("qr wrong code user=%r ip=%s", session.user.username, client_ip(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, WRONG_CODE)
    if not qr.approve(db, request_id, session.user.id, session.sid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    audit.info("qr approved user=%r approver_ip=%s requester_ip=%s", session.user.username, client_ip(request), row.requester_ip)
    notify(
        request, background, session.user, "qr_login",
        ip=row.requester_ip, ua=row.requester_user_agent or "?",
    )  # fmt: skip
    return QrStatusOut(status="approved")


@router.post("/{request_id}/deny", response_model=QrStatusOut)
def deny(
    request_id: str, request: Request, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db)
) -> QrStatusOut:
    open_request(db, request_id)
    if not qr.deny(db, request_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    audit.info("qr denied user=%r ip=%s", session.user.username, client_ip(request))
    return QrStatusOut(status="denied")
