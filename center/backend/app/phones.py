"""SMS one-time codes: issue, check and consume (mirrors emailtokens), plus the sending and throttle plumbing.

Only an HMAC of the code (keyed with a sub-key of JWT_SECRET, bound to the row id) is stored. A code is consumed
with a conditional UPDATE, so two concurrent submissions cannot both succeed.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, FastAPI, Request
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.audit import audit
from app.config import Settings
from app.models import PhoneCode, User
from app.phonenum import log_phone
from app.smsproviders import SmsProvider, make_provider
from app.throttle import AttemptThrottle
from sn_shared.security import get_jwt_secret

VERIFY = "verify"
LOGIN = "login"
TTL = {VERIFY: timedelta(minutes=10), LOGIN: timedelta(minutes=5)}
TTL_MINUTES = {VERIFY: 10, LOGIN: 5}
MAX_CODE_ATTEMPTS = 5
MAX_LIVE_CODES = 3  # live (unused) codes kept per (user, purpose)
CODE_DIGITS = 6

# Request budgets (SMS costs money and a number can be a victim: every request counts, known or not).
WINDOW = 900.0
LOGIN_SHARE = 0.7  # of SMS_DAILY_CAP: login sends; verification sends get the rest
WARN_SHARE = 0.8  # warn once when the whole daily cap is this used
USER_MAX_PER_DAY = 10
PHONE_MAX_PER_DAY = 10
CODE_FAIL_MAX_PER_IP_PHONE = 10
CODE_FAIL_MAX_PER_PHONE_ALL_IPS = 30
REQUEST_MAX_PER_IP = 10
REQUEST_MAX_PER_IP_PHONE = 2
REQUEST_MAX_PER_PHONE = 3
CHANGE_MAX_PER_USER_HOUR = 5
SUBMIT_MAX_PER_IP = 30
CODE_FAIL_WINDOW = 3600.0
DAY = 86400.0
DAILY_KEY = "all"

TEXTS = {
    VERIFY: "Mã xác minh số điện thoại của bạn là {code}. Có hiệu lực 10 phút. Không chia sẻ mã này.",
    LOGIN: "Mã đăng nhập của bạn là {code}. Có hiệu lực 5 phút. Không chia sẻ mã này.",
}


def _no_sync(statement):
    return statement.execution_options(synchronize_session=False)


def _now() -> datetime:
    return models.utcnow()


def install_phone(app: FastAPI, settings: Settings, kv) -> None:
    """Build the provider (refuses unsafe config) and the throttles; routes read them from `app.state`."""
    state = app.state
    state.sms = make_provider(settings, state.mailer)
    t = lambda n, m, w: AttemptThrottle(m, w, name=n, kv=kv)  # noqa: E731
    state.sms_ip_throttle = t("sms_ip", REQUEST_MAX_PER_IP, WINDOW)
    state.sms_ip_phone_throttle = t("sms_ip_phone", REQUEST_MAX_PER_IP_PHONE, WINDOW)
    state.sms_phone_throttle = t("sms_phone", REQUEST_MAX_PER_PHONE, WINDOW)
    state.sms_user_throttle = t("sms_user", CHANGE_MAX_PER_USER_HOUR, 3600.0)
    state.sms_submit_throttle = t("sms_submit", SUBMIT_MAX_PER_IP, WINDOW)
    state.sms_fail_throttle = t("sms_fail", CODE_FAIL_MAX_PER_IP_PHONE, CODE_FAIL_WINDOW)
    state.sms_fail_phone_throttle = t("sms_fail_phone", CODE_FAIL_MAX_PER_PHONE_ALL_IPS, CODE_FAIL_WINDOW)
    state.sms_user_day_throttle = t("sms_user_day", USER_MAX_PER_DAY, DAY)
    state.sms_phone_day_throttle = t("sms_phone_day", PHONE_MAX_PER_DAY, DAY)
    login_cap = max(1, int(settings.sms_daily_cap * LOGIN_SHARE))
    state.sms_daily_throttle = {
        LOGIN: t("sms_daily_login", login_cap, DAY),
        VERIFY: t("sms_daily_verify", max(1, settings.sms_daily_cap - login_cap), DAY),
    }
    state.sms_daily_warn_at = max(1, int(settings.sms_daily_cap * WARN_SHARE))


def _code_key() -> bytes:
    return hmac.new(get_jwt_secret().encode(), b"phone-code-subkey", hashlib.sha256).digest()


def code_mac(row_id: int, code: str) -> str:
    return hmac.new(_code_key(), f"{row_id}:{code}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"


def purge(db: Session) -> None:
    db.execute(_no_sync(delete(PhoneCode).where(or_(PhoneCode.expires_at < _now(), PhoneCode.used_at.is_not(None)))))


def _insert(db: Session, user_id: int, purpose: str, phone: str, code: str) -> PhoneCode:
    now = _now()
    row = PhoneCode(user_id=user_id, purpose=purpose, phone=phone, expires_at=now + TTL[purpose], created_at=now)
    db.add(row)
    db.flush()  # the code is bound to the row id
    row.code_hash = code_mac(row.id, code)
    return row


def _trim_live(db: Session, user_id: int, purpose: str) -> None:
    stale = db.scalars(
        select(PhoneCode.id)
        .where(PhoneCode.user_id == user_id, PhoneCode.purpose == purpose, PhoneCode.used_at.is_(None))
        .order_by(PhoneCode.id.desc())
        .offset(MAX_LIVE_CODES)
    ).all()
    if stale:
        db.execute(_no_sync(delete(PhoneCode).where(PhoneCode.id.in_(stale))))


def issue(db: Session, user: User | None, purpose: str, phone: str) -> str:
    """Create a code for `user`; with `user=None` do the same database work under a savepoint and store nothing."""
    purge(db)
    code = new_code()
    if user is None:
        owner = db.scalar(select(User.id).limit(1))
        savepoint = db.begin_nested()
        try:
            if owner is not None:
                _insert(db, owner, purpose, phone, code)
                _trim_live(db, owner, purpose)
        except IntegrityError:
            pass
        finally:
            savepoint.rollback()
        db.commit()
        return code
    _insert(db, user.id, purpose, phone, code)
    _trim_live(db, user.id, purpose)
    db.commit()
    return code


def find_for_user(db: Session, user_id: int, purpose: str, phone: str | None = None) -> PhoneCode | None:
    query = select(PhoneCode).where(
        PhoneCode.user_id == user_id, PhoneCode.purpose == purpose, PhoneCode.used_at.is_(None),
        PhoneCode.expires_at > _now(), PhoneCode.attempts < MAX_CODE_ATTEMPTS,
    )
    if phone is not None:
        query = query.where(PhoneCode.phone == phone)
    return db.scalar(query.order_by(PhoneCode.id.desc()))


def check_code(db: Session, row: PhoneCode | None, code: str) -> bool:
    """Count one attempt (persisted) and compare in constant time; a missing row costs the same MAC."""
    code = code.strip()
    if row is None:
        hmac.compare_digest(code_mac(0, code), code_mac(0, ""))
        return False
    counted = db.execute(
        _no_sync(
            update(PhoneCode)
            .where(PhoneCode.id == row.id, PhoneCode.used_at.is_(None), PhoneCode.attempts < MAX_CODE_ATTEMPTS)
            .values(attempts=PhoneCode.attempts + 1)
        )
    )
    db.commit()
    if counted.rowcount != 1 or row.code_hash is None:
        return False
    return hmac.compare_digest(code_mac(row.id, code), row.code_hash)


def consume(db: Session, row_id: int) -> bool:
    result = db.execute(
        _no_sync(
            update(PhoneCode)
            .where(PhoneCode.id == row_id, PhoneCode.used_at.is_(None), PhoneCode.expires_at > _now())
            .values(used_at=_now())
        )
    )
    return result.rowcount == 1


def drop_codes(db: Session, user_id: int, purpose: str) -> None:
    db.execute(_no_sync(delete(PhoneCode).where(PhoneCode.user_id == user_id, PhoneCode.purpose == purpose)))


def _deliver(provider: SmsProvider, phone: str, text: str) -> None:
    try:
        provider.send(phone, text)
    except Exception as exc:  # noqa: BLE001 - a provider problem must never reach the client
        audit.warning("sms failed to=%s error=%s", log_phone(phone), type(exc).__name__)
    else:
        audit.info("sms sent to=%s", log_phone(phone))


def spend_daily(request: Request, purpose: str) -> bool:
    """Count one REAL send against this flow's share of the daily cap; False when the share is spent."""
    state = request.app.state
    if not state.sms_daily_throttle[purpose].check_and_record(DAILY_KEY):
        audit.warning("sms daily cap reached purpose=%s", purpose)
        return False
    total = sum(t.count(DAILY_KEY) for t in state.sms_daily_throttle.values())
    if total == state.sms_daily_warn_at:
        audit.warning("sms daily cap at %d%% (%d sends)", int(WARN_SHARE * 100), total)
    return True


def queue_sms(request: Request, background: BackgroundTasks, purpose: str, phone: str, code: str) -> None:
    """Queue one REAL send (the caller has already counted it against the daily cap)."""
    background.add_task(_deliver, request.app.state.sms, phone, TEXTS[purpose].format(code=code))
