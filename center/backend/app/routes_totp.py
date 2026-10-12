"""TOTP second factor: set up / enable / disable, recovery codes, and the second login step.

Managing routes need the session, CSRF and a re-auth like every sensitive account change. Every failure at the
login step is the same 401 and never says why (wrong code, replay, used recovery code, bad token, TOTP off).
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app import totp
from app.audit import audit
from app.db import get_db
from app.deps import AuthSession, check_origin, client_ip, csrf_session, require_reauth, settings_of, too_many
from app.models import RecoveryCode, User
from app.notify import notify
from app.schemas import DeleteAccountBody, RecoveryCodesOut, SessionOut, TotpCodeBody, TotpLoginBody, TotpSetupOut
from app.sessions import issue_session
from app.tokens import decode_typed
from app.tokenversion import bump_token_version
from sn_shared.security import AuthError

INVALID_CODE = "Invalid code"
ALREADY_ENABLED = "Two-step verification is already enabled"
NOT_ENABLED = "Two-step verification is not enabled"

router = APIRouter(prefix="/auth", tags=["totp"], dependencies=[Depends(check_origin)])


def _cipher(request: Request):
    return request.app.state.totp_cipher


def _clear_totp(db: Session, user: User) -> None:
    """Straight UPDATE/DELETE: the instance may be stale after the atomic UPDATEs of this request."""
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(totp_enabled=False, totp_secret=None, totp_pending_secret=None, totp_last_step=None)
        .execution_options(synchronize_session=False)
    )
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id).execution_options(synchronize_session=False))


# --- managing (signed in) --------------------------------------------------------------------------------


def _manage_keys(request: Request, user: User) -> list[str]:
    """Wrong codes while managing TOTP are throttled per (address, user) and per user; 429 when locked."""
    keys = [f"{client_ip(request)}|{user.id}", str(user.id)]
    if any(request.app.state.totp_manage_throttle.is_blocked(k) for k in keys):
        audit.warning("totp manage locked user=%r ip=%s", user.username, client_ip(request))
        raise too_many()
    return keys


def _reject_code(request: Request, db: Session, user: User, keys: list[str]) -> HTTPException:
    for key in keys:
        request.app.state.totp_manage_throttle.record(key)
    db.rollback()
    audit.warning("totp code rejected user=%r ip=%s", user.username, client_ip(request))
    return HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_CODE)


def _forgive(request: Request, keys: list[str]) -> None:
    for key in keys:
        request.app.state.totp_manage_throttle.reset(key)


@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(
    request: Request,
    body: DeleteAccountBody | None = None,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> TotpSetupOut:
    """Start (or restart) enrolment: a new pending secret replaces any earlier one. Body: {password} for re-auth."""
    user = session.user
    require_reauth(request, user, body.password if body else None)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_ENABLED)
    secret = totp.new_secret()
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.totp_enabled.is_(False))
        .values(totp_pending_secret=totp.seal(_cipher(request), secret))
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_ENABLED)
    db.commit()
    audit.info("totp setup started user=%r ip=%s", user.username, client_ip(request))
    return TotpSetupOut(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.username))


@router.post("/totp/enable", response_model=RecoveryCodesOut)
def totp_enable(
    body: TotpCodeBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> RecoveryCodesOut:
    """Verify the pending secret, turn TOTP on and return the recovery codes (shown once).

    Other sessions and refresh tokens are revoked (token_version bump) and this session is re-issued; the new
    `csrf_token` is in the body. Known limitation: for an account without a password (passkey/Google only)
    require_reauth is a no-op, so a stolen session can enrol; the bump at least ends the thief's other sessions.
    """
    user = session.user
    require_reauth(request, user, body.password)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_ENABLED)
    keys = _manage_keys(request, user)
    pending = user.totp_pending_secret
    step = totp.matching_step(totp.unseal(_cipher(request), pending), body.code)
    if step is None:
        raise _reject_code(request, db, user, keys)
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.totp_enabled.is_(False), User.totp_pending_secret == pending)
        .values(totp_enabled=True, totp_secret=pending, totp_pending_secret=None, totp_last_step=step)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise _reject_code(request, db, user, keys)
    codes = totp.replace_recovery_codes(db, user.id)
    bump_token_version(db, user)
    db.commit()
    _forgive(request, keys)
    fresh = issue_session(response, user, settings_of(request))
    audit.info("totp enabled user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "totp_enabled")
    return RecoveryCodesOut(recovery_codes=codes, csrf_token=fresh.csrf_token)


@router.delete("/totp", status_code=status.HTTP_204_NO_CONTENT)
def totp_disable(
    body: TotpCodeBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> None:
    """Needs a current TOTP code or a recovery code. Other sessions die; this one is re-issued (use GET /auth/me)."""
    user = session.user
    require_reauth(request, user, body.password)
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ENABLED)
    keys = _manage_keys(request, user)
    if not (totp.check_totp(db, _cipher(request), user, body.code) or totp.consume_recovery_code(db, user.id, body.code)):
        raise _reject_code(request, db, user, keys)
    _clear_totp(db, user)
    bump_token_version(db, user)
    db.commit()
    _forgive(request, keys)
    issue_session(response, user, settings_of(request))
    audit.info("totp disabled user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "totp_disabled")


@router.post("/totp/recovery-codes", response_model=RecoveryCodesOut)
def regenerate_recovery_codes(
    body: TotpCodeBody,
    request: Request,
    background: BackgroundTasks,
    session: AuthSession = Depends(csrf_session),
    db: Session = Depends(get_db),
) -> RecoveryCodesOut:
    user = session.user
    require_reauth(request, user, body.password)
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ENABLED)
    keys = _manage_keys(request, user)
    if not totp.check_totp(db, _cipher(request), user, body.code):
        raise _reject_code(request, db, user, keys)
    codes = totp.replace_recovery_codes(db, user.id)
    db.commit()
    _forgive(request, keys)
    audit.info("recovery codes regenerated user=%r ip=%s", user.username, client_ip(request))
    notify(request, background, user, "recovery_codes_regenerated")
    return RecoveryCodesOut(recovery_codes=codes)


# --- login (second step) ---------------------------------------------------------------------------------


def _login_user(db: Session, mfa_token: str) -> User | None:
    try:
        user_id, ver = decode_typed(mfa_token, "mfa")
    except AuthError:
        return None
    user = db.get(User, user_id)
    return user if user is not None and user.token_version == ver and user.totp_enabled else None


def _login_code_ok(request: Request, db: Session, user: User | None, body: TotpLoginBody) -> bool:
    """TOTP code or recovery code; failures cost about the same whether or not there is a real user behind them."""
    if body.recovery_code is not None:
        return totp.consume_recovery_code(db, user.id if user else 0, body.recovery_code) and user is not None
    if user is None:
        totp.matching_step(None, body.code or "")
        return False
    return totp.check_totp(db, _cipher(request), user, body.code or "")


@router.post("/login/totp", response_model=SessionOut)
def login_totp(
    body: TotpLoginBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SessionOut:
    """Second factor with an authenticator code or a recovery code; any one listed factor completes the login."""
    ip, state = client_ip(request), request.app.state
    if state.totp_login_ip_throttle.is_blocked(ip):
        audit.warning("totp login locked ip=%s", ip)
        raise too_many()
    user = _login_user(db, body.mfa_token)
    account = str(user.id) if user else None
    if account is not None and state.totp_login_account_throttle.is_blocked(account):
        audit.warning("totp login locked user=%r ip=%s", user.username, ip)
        raise too_many()
    state.totp_login_ip_throttle.record(ip)  # counted up front so parallel guesses cannot all slip through
    if account is not None:
        state.totp_login_account_throttle.record(account)
    if not _login_code_ok(request, db, user, body):
        db.rollback()
        audit.warning("mfa totp failed user=%r ip=%s", user.username if user else None, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CODE)
    db.commit()
    state.totp_login_ip_throttle.reset(ip)
    state.totp_login_account_throttle.reset(account)
    if body.recovery_code is not None:
        audit.warning("login ok (recovery code used) user=%r ip=%s", user.username, ip)
        notify(request, background, user, "recovery_code_used")
    else:
        audit.info("login ok (totp 2nd factor) user=%r ip=%s", user.username, ip)
    return issue_session(response, user, settings_of(request))
