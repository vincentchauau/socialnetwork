import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app.bodylimit import BodyLimitMiddleware, limit_for
from app.config import Settings
from app.crypto import TemplateCipher
from app.db import DEFAULT_DATABASE_URL, Base, make_engine
from app.events import EventRelay, redis_client_factory
from app.google_auth import make_google_verifier
from app.kv import Kv, make_kv
from app.mailer import SmtpMailer
from app.middleware import SecurityHeadersMiddleware
from app.migrate import ensure_columns, force_relogin, sessions_table_is_new
from app.passkeys import ChallengeStore
from app.liveness import ANALYSES_MAX_PER_IP as LIVENESS_ANALYSES_MAX_PER_IP
from app.liveness import ANALYSES_WINDOW_SECONDS as LIVENESS_ANALYSES_WINDOW_SECONDS
from app.liveness import warn_if_optional
from app.routes_liveness import liveness_router
from app.phones import install_phone
from app.routes_account import router as account_router
from app.routes_auth import router as auth_router
from app.routes_biometrics import router as biometrics_router
from app.routes_email import router as email_router
from app.routes_methods import combined_router, methods_router
from app.reauth import ReauthRequired, reauth_response
from app.routes_passkeys import router as passkeys_router
from app.routes_phone import router as phone_router
from app.routes_qr import router as qr_router
from app.routes_reauth import router as reauth_router
from app.routes_sessions import router as sessions_router
from app.routes_totp import router as totp_router
from app.throttle import AttemptThrottle
from app.totp import make_cipher

LOGIN_MAX_FAILURES_PER_IP_USER = 5  # per (client address, username)
LOGIN_MAX_FAILURES_PER_IP = 20  # across all usernames from one address
LOGIN_ACCOUNT_FACTOR = 4  # per account, across all addresses
REGISTER_MAX_PER_IP = 10
REGISTER_WINDOW_SECONDS = 600.0
REFRESH_MAX_PER_IP = 60
REFRESH_WINDOW_SECONDS = 300.0
REAUTH_MAX_FAILURES = 5
BIOMETRIC_MAX_FAILURES = 5  # second factor, per (ip, user)
BIOMETRIC_ONLY_MAX_ATTEMPTS = 3  # passwordless login, per (ip, user)
BIOMETRIC_WINDOW_SECONDS = 900.0
BIOMETRIC_ACCOUNT_FACTOR = 4
IDENTIFY_MAX_PER_IP = 5  # username-less webcam sign-in attempts per address per window
IDENTIFY_GLOBAL_MAX = 100  # ... across all addresses (protects CPU: each attempt is O(candidates))
PASSKEY_OPTIONS_MAX_PER_IP = 30  # option requests (sign-in, sign-up, link) per address per window
PASSKEY_OPTIONS_WINDOW_SECONDS = 600.0
PASSKEY_LOGIN_MAX_FAILURES_PER_IP = 10  # failed passkey sign-ins per address per window
PASSKEY_LOGIN_WINDOW_SECONDS = 900.0
ENROLL_MAX_PER_HOUR = 10
MAX_CONCURRENT_BIOMETRICS = 2
EMAIL_REQUEST_MAX_PER_IP = 5  # login-link / forgot-password requests per address per window
EMAIL_REQUEST_MAX_PER_IP_ADDRESS = 3  # ... per (address, normalised email): one IP cannot spend the email's budget
EMAIL_REQUEST_MAX_PER_ADDRESS = 10  # ... per normalised email across all addresses (same for known and unknown)
EMAIL_REQUEST_WINDOW_SECONDS = 900.0
EMAIL_SUBMIT_MAX_PER_IP = 20  # codes, links and reset submissions per address per window
EMAIL_CODE_MAX_FAILURES_PER_ADDRESS = 10  # wrong code submissions per normalised email, across rows
EMAIL_CODE_FAILURE_WINDOW_SECONDS = 3600.0
EMAIL_CHANGE_MAX_PER_HOUR = 5  # verification mails per user
EMAIL_CHANGE_MAX_PER_TARGET = 3  # verification mails per target address from the change-email route
TOTP_LOGIN_MAX_PER_IP = 20  # wrong TOTP/recovery codes at the second step, per address per window
TOTP_LOGIN_MAX_PER_ACCOUNT = 10  # ... per account, across all addresses
TOTP_MANAGE_MAX_FAILURES = 5  # wrong codes on enable/disable/regenerate, per (address, user)
TOTP_WINDOW_SECONDS = 900.0
FRESH_MAX_FAILURES = 5  # failed step-up proofs (passkey, Google, mailed code), per user
FRESH_WINDOW_SECONDS = 900.0
FRESH_MAX_FAILURES = 5  # failed step-up proofs (passkey, Google, mailed code), per user
FRESH_WINDOW_SECONDS = 900.0
LIVENESS_CHALLENGES_MAX_PER_IP = 20  # liveness challenges per address per minute
RENAME_MAX_PER_DAY = 10  # username change attempts per user (the 30-day rule is separate)
REGISTER_MAIL_MAX_PER_ADDRESS = 3  # verification mails triggered by sign-ups, per target address
QR_START_MAX_PER_IP = 10  # QR sign-in requests per address per window
QR_POLL_MAX_PER_IP = 200  # polls (every ~2 s while a code is shown) per address per window
QR_WINDOW_SECONDS = 300.0


def _install_throttles(app: FastAPI, kv: Kv) -> None:
    state = app.state
    state.kv = kv
    state.login_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_IP_USER, name="login_throttle", kv=kv)
    state.login_ip_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_IP, name="login_ip_throttle", kv=kv)
    state.login_account_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_IP_USER * LOGIN_ACCOUNT_FACTOR, name="login_account_throttle", kv=kv)
    state.register_throttle = AttemptThrottle(max_attempts=REGISTER_MAX_PER_IP, window_seconds=REGISTER_WINDOW_SECONDS, name="register_throttle", kv=kv)
    state.refresh_throttle = AttemptThrottle(max_attempts=REFRESH_MAX_PER_IP, window_seconds=REFRESH_WINDOW_SECONDS, name="refresh_throttle", kv=kv)
    state.reauth_throttle = AttemptThrottle(max_attempts=REAUTH_MAX_FAILURES, name="reauth_throttle", kv=kv)
    window = BIOMETRIC_WINDOW_SECONDS
    state.bio_throttle = AttemptThrottle(BIOMETRIC_MAX_FAILURES, window, name="bio_throttle", kv=kv)
    state.bio_account_throttle = AttemptThrottle(BIOMETRIC_MAX_FAILURES * BIOMETRIC_ACCOUNT_FACTOR, window, name="bio_account_throttle", kv=kv)
    state.alone_throttle = AttemptThrottle(BIOMETRIC_ONLY_MAX_ATTEMPTS, window, name="alone_throttle", kv=kv)
    state.alone_account_throttle = AttemptThrottle(BIOMETRIC_ONLY_MAX_ATTEMPTS * BIOMETRIC_ACCOUNT_FACTOR, window, name="alone_account_throttle", kv=kv)
    state.identify_ip_throttle = AttemptThrottle(IDENTIFY_MAX_PER_IP, window, name="identify_ip_throttle", kv=kv)
    state.identify_global_throttle = AttemptThrottle(IDENTIFY_GLOBAL_MAX, window, name="identify_global_throttle", kv=kv)
    # voice identification has its own counters: voice and face attempts never lock each other out
    state.voice_identify_ip_throttle = AttemptThrottle(IDENTIFY_MAX_PER_IP, window, name="voice_identify_ip_throttle", kv=kv)
    state.voice_identify_global_throttle = AttemptThrottle(IDENTIFY_GLOBAL_MAX, window, name="voice_identify_global_throttle", kv=kv)
    state.passkey_options_throttle = AttemptThrottle(PASSKEY_OPTIONS_MAX_PER_IP, PASSKEY_OPTIONS_WINDOW_SECONDS, name="passkey_options_throttle", kv=kv)
    state.passkey_login_throttle = AttemptThrottle(PASSKEY_LOGIN_MAX_FAILURES_PER_IP, PASSKEY_LOGIN_WINDOW_SECONDS, name="passkey_login_throttle", kv=kv)
    state.liveness_throttle = AttemptThrottle(LIVENESS_CHALLENGES_MAX_PER_IP, 60.0, name="liveness_throttle", kv=kv)
    state.liveness_analysis_throttle = AttemptThrottle(
        LIVENESS_ANALYSES_MAX_PER_IP, LIVENESS_ANALYSES_WINDOW_SECONDS, name="liveness_analysis_throttle", kv=kv
    )
    state.passkey_challenges = ChallengeStore(kv)  # consumed challenge ids; shared like the throttles
    state.enroll_throttle = AttemptThrottle(ENROLL_MAX_PER_HOUR, 3600.0, name="enroll_throttle", kv=kv)
    window = EMAIL_REQUEST_WINDOW_SECONDS
    state.email_login_ip_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_IP, window, name="email_login_ip_throttle", kv=kv)
    state.email_login_ip_addr_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_IP_ADDRESS, window, name="email_login_ip_addr_throttle", kv=kv)
    state.email_login_addr_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_ADDRESS, window, name="email_login_addr_throttle", kv=kv)
    state.forgot_ip_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_IP, window, name="forgot_ip_throttle", kv=kv)
    state.forgot_ip_addr_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_IP_ADDRESS, window, name="forgot_ip_addr_throttle", kv=kv)
    state.forgot_addr_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_ADDRESS, window, name="forgot_addr_throttle", kv=kv)
    state.email_submit_throttle = AttemptThrottle(EMAIL_SUBMIT_MAX_PER_IP, window, name="email_submit_throttle", kv=kv)
    state.email_code_fail_throttle = AttemptThrottle(EMAIL_CODE_MAX_FAILURES_PER_ADDRESS, EMAIL_CODE_FAILURE_WINDOW_SECONDS, name="email_code_fail_throttle", kv=kv)
    state.email_change_throttle = AttemptThrottle(EMAIL_CHANGE_MAX_PER_HOUR, 3600.0, name="email_change_throttle", kv=kv)
    state.email_change_target_throttle = AttemptThrottle(EMAIL_CHANGE_MAX_PER_TARGET, window, name="email_change_target_throttle", kv=kv)
    state.register_mail_throttle = AttemptThrottle(REGISTER_MAIL_MAX_PER_ADDRESS, window, name="register_mail_throttle", kv=kv)
    state.totp_login_ip_throttle = AttemptThrottle(TOTP_LOGIN_MAX_PER_IP, TOTP_WINDOW_SECONDS, name="totp_login_ip_throttle", kv=kv)
    state.totp_login_account_throttle = AttemptThrottle(TOTP_LOGIN_MAX_PER_ACCOUNT, TOTP_WINDOW_SECONDS, name="totp_login_account_throttle", kv=kv)
    state.totp_manage_throttle = AttemptThrottle(TOTP_MANAGE_MAX_FAILURES, TOTP_WINDOW_SECONDS, name="totp_manage_throttle", kv=kv)
    state.fresh_throttle = AttemptThrottle(FRESH_MAX_FAILURES, FRESH_WINDOW_SECONDS, name="fresh_throttle", kv=kv)
    state.reauth_mail_ip_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_IP, window, name="reauth_mail_ip_throttle", kv=kv)
    state.reauth_mail_ip_addr_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_IP_ADDRESS, window, name="reauth_mail_ip_addr_throttle", kv=kv)
    state.reauth_mail_addr_throttle = AttemptThrottle(EMAIL_REQUEST_MAX_PER_ADDRESS, window, name="reauth_mail_addr_throttle", kv=kv)
    state.rename_throttle = AttemptThrottle(RENAME_MAX_PER_DAY, 86400.0, name="rename_throttle", kv=kv)
    state.qr_start_throttle = AttemptThrottle(QR_START_MAX_PER_IP, QR_WINDOW_SECONDS, name="qr_start_throttle", kv=kv)
    state.qr_poll_throttle = AttemptThrottle(QR_POLL_MAX_PER_IP, QR_WINDOW_SECONDS, name="qr_poll_throttle", kv=kv)
    state.biometric_slots = threading.BoundedSemaphore(MAX_CONCURRENT_BIOMETRICS)


def _install_biometrics(app: FastAPI, settings: Settings) -> None:
    app.state.biometrics = None
    app.state.cipher = None
    if settings.biometrics_enabled:
        from app.biometrics import RealBiometrics  # heavy libraries load lazily inside

        app.state.cipher = TemplateCipher(settings.data_key)  # fails at startup on a bad key
        app.state.biometrics = RealBiometrics(settings)
        warn_if_optional(settings)


def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", ())[1:])
    message = str(first.get("msg", "Invalid request")).removeprefix("Value error, ")
    return JSONResponse({"detail": f"{field}: {message}" if field else message}, status_code=422)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = Settings.from_env()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    first_with_sessions = sessions_table_is_new(engine)
    Base.metadata.create_all(engine)
    ensure_columns(engine)  # upgrade a users table created by an older version
    if first_with_sessions:
        force_relogin(engine)  # tokens without a sid cannot be revoked: end them all, once

    docs = None if settings.production else "/docs"
    relay_holder: list[EventRelay] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        relay_holder[0].start()  # a no-op without REDIS_URL: outbox rows then stay until Redis is configured
        try:
            yield
        finally:
            relay_holder[0].stop()

    app = FastAPI(
        lifespan=lifespan,
        title="socialnetwork center",
        docs_url=docs,
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.event_relay = EventRelay(app.state.session_factory, redis_client_factory(settings.redis_url))
    relay_holder.append(app.state.event_relay)
    _install_throttles(app, make_kv(settings.redis_url))
    _install_biometrics(app, settings)
    app.state.totp_cipher = make_cipher(settings)  # fails at startup on a bad DATA_KEY
    app.state.google_verifier = (
        make_google_verifier(settings.google_client_id) if settings.google_client_id else None
    )
    app.state.mailer = (
        SmtpMailer(
            settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_from,
            starttls=settings.smtp_starttls, use_ssl=settings.smtp_ssl,
        )
        if settings.email_enabled
        else None
    )
    install_phone(app, settings, app.state.kv)  # SMS provider + throttles (refuses SMS_PROVIDER=mailbox in production)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(ReauthRequired, reauth_response)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(email_router)
    app.include_router(phone_router)
    app.include_router(biometrics_router)
    app.include_router(methods_router)
    app.include_router(liveness_router)
    app.include_router(combined_router)
    app.include_router(passkeys_router)
    app.include_router(totp_router)
    app.include_router(sessions_router)
    app.include_router(reauth_router)
    app.include_router(qr_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "redis": app.state.kv.probe()}

    enabled = settings.biometrics_enabled
    app.add_middleware(BodyLimitMiddleware, limit=lambda path: limit_for(path, enabled))
    app.add_middleware(SecurityHeadersMiddleware)
    return app


app = create_app()
