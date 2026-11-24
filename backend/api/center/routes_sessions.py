"""The signed-in devices of the account: list them, revoke one, revoke all the others.

Revoking sets `revoked_at` AND publishes the sid to the revocation store, so every app rejects that device's
access token at once (center itself checks the row on every request and refresh). Own sessions only: any other
sid, known or not, is the same 404. These routes are exempt from re-authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from api.center import usersessions
from api.center.audit import audit
from api.center.db import get_db
from api.center.deps import AuthSession, check_origin, client_ip, csrf_session, current_session, settings_of
from api.center.models import UserSession
from api.center.schemas import RevokedOut, SessionItem
from api.center.sessions import clear_session_cookies
from api.center.tokenversion import access_ttl_seconds

NOT_FOUND = "Session not found"

router = APIRouter(prefix="/auth", tags=["sessions"], dependencies=[Depends(check_origin)])


def _item(row: UserSession, current_sid: str | None) -> SessionItem:
    return SessionItem(
        id=row.sid, current=row.sid == current_sid, created_at=usersessions.as_utc(row.created_at),
        last_seen_at=usersessions.as_utc(row.last_seen_at), ip=row.ip, user_agent=row.user_agent, method=row.method,
    )  # fmt: skip


@router.get("/sessions", response_model=list[SessionItem])
def list_sessions(session: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> list[SessionItem]:
    return [_item(row, session.sid) for row in usersessions.active_sessions(db, session.user.id)]


@router.post("/sessions/revoke-others", response_model=RevokedOut)
def revoke_other_sessions(
    request: Request, session: AuthSession = Depends(csrf_session), db: Session = Depends(get_db)
) -> RevokedOut:
    others = [row for row in usersessions.active_sessions(db, session.user.id) if row.sid != session.sid]
    count = usersessions.revoke(db, others, access_ttl_seconds(settings_of(request)))
    audit.info("sessions revoked user=%r count=%d ip=%s", session.user.username, count, client_ip(request))
    return RevokedOut(revoked=count)


@router.delete("/sessions/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    sid: str, request: Request, response: Response, session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> None:
    row = usersessions.live_session(db, sid, session.user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    settings = settings_of(request)
    usersessions.revoke(db, [row], access_ttl_seconds(settings))
    if sid == session.sid:
        clear_session_cookies(response, settings)
    audit.info("session revoked user=%r ip=%s", session.user.username, client_ip(request))
