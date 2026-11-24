from sn_shared.deps import access_dependencies
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sn_shared import skills
from sqlalchemy.orm import sessionmaker

from api.center.bodylimit import BodyLimitMiddleware, limit_for
from api.center.admin import records as records_router
from api.center.config import Settings
from api.center.crypto import TemplateCipher
from api.center.db import DEFAULT_DATABASE_URL, Base, make_engine
from api.center.events import EventRelay, redis_client_factory
from api.center.google_auth import make_google_verifier
from api.center.kv import Kv, make_kv
from api.center.mailer import SmtpMailer
from api.center.middleware import SecurityHeadersMiddleware
from api.center.migrate import ensure_columns, force_relogin, sessions_table_is_new
from api.center.passkeys import ChallengeStore
from api.center.system_user import ensure_system_user
from api.center.liveness import warn_if_optional
from api.center.routes_liveness import router as liveness_router
from api.center.phones import install_phone
from api.center.routes_account import router as account_router
from api.center.routes_auth import router as auth_router
from api.center.routes_biometrics import router as biometrics_router
from api.center.routes_email import router as email_router
from api.center.routes_methods import combined_router, router as methods_router
from api.center.reauth import ReauthRequired, reauth_response
from api.center.routes_passkeys import router as passkeys_router
from api.center.routes_phone import router as phone_router
from api.center.routes_profile import router as profile_router
from api.center.routes_qr import router as qr_router
from api.center.routes_reauth import router as reauth_router
from api.center.routes_sessions import router as sessions_router
from api.center.routes_totp import router as totp_router
from api.center.throttle import AttemptThrottle
from api.center.totp import make_cipher

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
LIVENESS_CHALLENGES_MAX_PER_IP = 20  # liveness challenges per address per minute
RENAME_MAX_PER_DAY = 10  # username change attempts per user (the 30-day rule is separate)
REGISTER_MAIL_MAX_PER_ADDRESS = 3  # verification mails triggered by sign-ups, per target address
QR_START_MAX_PER_IP = 10  # QR sign-in requests per address per window
QR_POLL_MAX_PER_IP = 200  # polls (every ~2 s while a code is shown) per address per window
QR_WINDOW_SECONDS = 300.0
LIVENESS_WINDOW_SECONDS = 60.0


DEFAULT_WINDOW_SECONDS = 300.0
HOUR_SECONDS = 3600.0
DAY_SECONDS = 24 * HOUR_SECONDS

# attribute name on app.state -> (max attempts, window seconds). The name also namespaces the throttle's keys
# in the shared Kv, so replicas must agree on it: never rename one without accepting a counter reset.
THROTTLES: dict[str, tuple[int, float]] = {
    "login_throttle": (LOGIN_MAX_FAILURES_PER_IP_USER, DEFAULT_WINDOW_SECONDS),
    "login_ip_throttle": (LOGIN_MAX_FAILURES_PER_IP, DEFAULT_WINDOW_SECONDS),
    "login_account_throttle": (LOGIN_MAX_FAILURES_PER_IP_USER * LOGIN_ACCOUNT_FACTOR, DEFAULT_WINDOW_SECONDS),
    "register_throttle": (REGISTER_MAX_PER_IP, REGISTER_WINDOW_SECONDS),
    "refresh_throttle": (REFRESH_MAX_PER_IP, REFRESH_WINDOW_SECONDS),
    "reauth_throttle": (REAUTH_MAX_FAILURES, DEFAULT_WINDOW_SECONDS),
    "bio_throttle": (BIOMETRIC_MAX_FAILURES, BIOMETRIC_WINDOW_SECONDS),
    "bio_account_throttle": (BIOMETRIC_MAX_FAILURES * BIOMETRIC_ACCOUNT_FACTOR, BIOMETRIC_WINDOW_SECONDS),
    "alone_throttle": (BIOMETRIC_ONLY_MAX_ATTEMPTS, BIOMETRIC_WINDOW_SECONDS),
    "alone_account_throttle": (BIOMETRIC_ONLY_MAX_ATTEMPTS * BIOMETRIC_ACCOUNT_FACTOR, BIOMETRIC_WINDOW_SECONDS),
    "identify_ip_throttle": (IDENTIFY_MAX_PER_IP, BIOMETRIC_WINDOW_SECONDS),
    "identify_global_throttle": (IDENTIFY_GLOBAL_MAX, BIOMETRIC_WINDOW_SECONDS),
    # voice identification has its own counters: voice and face attempts never lock each other out
    "voice_identify_ip_throttle": (IDENTIFY_MAX_PER_IP, BIOMETRIC_WINDOW_SECONDS),
    "voice_identify_global_throttle": (IDENTIFY_GLOBAL_MAX, BIOMETRIC_WINDOW_SECONDS),
    "passkey_options_throttle": (PASSKEY_OPTIONS_MAX_PER_IP, PASSKEY_OPTIONS_WINDOW_SECONDS),
    "passkey_login_throttle": (PASSKEY_LOGIN_MAX_FAILURES_PER_IP, PASSKEY_LOGIN_WINDOW_SECONDS),
    "enroll_throttle": (ENROLL_MAX_PER_HOUR, HOUR_SECONDS),
    "email_login_ip_throttle": (EMAIL_REQUEST_MAX_PER_IP, EMAIL_REQUEST_WINDOW_SECONDS),
    "email_login_ip_addr_throttle": (EMAIL_REQUEST_MAX_PER_IP_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
    "email_login_addr_throttle": (EMAIL_REQUEST_MAX_PER_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
    "forgot_ip_throttle": (EMAIL_REQUEST_MAX_PER_IP, EMAIL_REQUEST_WINDOW_SECONDS),
    "forgot_ip_addr_throttle": (EMAIL_REQUEST_MAX_PER_IP_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
    "forgot_addr_throttle": (EMAIL_REQUEST_MAX_PER_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
    "email_submit_throttle": (EMAIL_SUBMIT_MAX_PER_IP, EMAIL_REQUEST_WINDOW_SECONDS),
    "email_code_fail_throttle": (EMAIL_CODE_MAX_FAILURES_PER_ADDRESS, EMAIL_CODE_FAILURE_WINDOW_SECONDS),
    "email_change_throttle": (EMAIL_CHANGE_MAX_PER_HOUR, HOUR_SECONDS),
    "email_change_target_throttle": (EMAIL_CHANGE_MAX_PER_TARGET, EMAIL_REQUEST_WINDOW_SECONDS),
    "register_mail_throttle": (REGISTER_MAIL_MAX_PER_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
    "totp_login_ip_throttle": (TOTP_LOGIN_MAX_PER_IP, TOTP_WINDOW_SECONDS),
    "totp_login_account_throttle": (TOTP_LOGIN_MAX_PER_ACCOUNT, TOTP_WINDOW_SECONDS),
    "totp_manage_throttle": (TOTP_MANAGE_MAX_FAILURES, TOTP_WINDOW_SECONDS),
    "rename_throttle": (RENAME_MAX_PER_DAY, DAY_SECONDS),
    "fresh_throttle": (FRESH_MAX_FAILURES, FRESH_WINDOW_SECONDS),
    "liveness_throttle": (LIVENESS_CHALLENGES_MAX_PER_IP, LIVENESS_WINDOW_SECONDS),
    "liveness_analysis_throttle": (LIVENESS_CHALLENGES_MAX_PER_IP, LIVENESS_WINDOW_SECONDS),
    "qr_start_throttle": (QR_START_MAX_PER_IP, QR_WINDOW_SECONDS),
    "qr_poll_throttle": (QR_POLL_MAX_PER_IP, QR_WINDOW_SECONDS),
    # a mailed re-authentication code: same budgets as the other mails, counted apart so they never lock each other out
    "reauth_mail_ip_throttle": (EMAIL_REQUEST_MAX_PER_IP, EMAIL_REQUEST_WINDOW_SECONDS),
    "reauth_mail_ip_addr_throttle": (EMAIL_REQUEST_MAX_PER_IP_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
    "reauth_mail_addr_throttle": (EMAIL_REQUEST_MAX_PER_ADDRESS, EMAIL_REQUEST_WINDOW_SECONDS),
}


def _install_throttles(app: FastAPI, kv: Kv) -> None:
    state = app.state
    state.kv = kv
    for name, (max_attempts, window) in THROTTLES.items():
        setattr(state, name, AttemptThrottle(max_attempts, window, name=name, kv=kv))
    state.passkey_challenges = ChallengeStore(kv)  # consumed challenge ids; shared like the throttles
    state.biometric_slots = threading.BoundedSemaphore(MAX_CONCURRENT_BIOMETRICS)


def _install_biometrics(app: FastAPI, settings: Settings) -> None:
    app.state.biometrics = None
    app.state.cipher = None
    if settings.biometrics_enabled:
        from api.center.biometrics import RealBiometrics  # heavy libraries load lazily inside

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
    skills.ensure_tables(engine)  # the vocabulary of skills that profiles, jobs and courses share (`sn_shared.skills`)
    ensure_columns(engine)  # upgrade a users table created by an older version
    if first_with_sessions:
        force_relogin(engine)  # tokens without a sid cannot be revoked: end them all, once
    if os.environ.get("SYSTEM_USER", "1") != "0":  # SYSTEM_USER=0: no account `system` (the tests of center count the users they make)
        with sessionmaker(engine, expire_on_commit=False)() as setup:
            ensure_system_user(setup)  # the voice of the chat's lines about its rooms

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
    app.include_router(auth_router, dependencies=access_dependencies(public=True))
    app.include_router(account_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(profile_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(email_router, dependencies=access_dependencies(public=True))
    app.include_router(phone_router, dependencies=access_dependencies(public=True))
    app.include_router(biometrics_router, dependencies=access_dependencies(public=True))
    app.include_router(methods_router, dependencies=access_dependencies(public=True))
    app.include_router(liveness_router, dependencies=access_dependencies(public=True))
    app.include_router(combined_router, dependencies=access_dependencies(public=True))
    app.include_router(passkeys_router, dependencies=access_dependencies(public=True))
    app.include_router(totp_router, dependencies=access_dependencies(public=True))
    app.include_router(sessions_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(reauth_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(qr_router, dependencies=access_dependencies(public=True))
    app.include_router(records_router(), prefix="/records")

    @app.get("/health", dependencies=access_dependencies(public=True))
    def health() -> dict[str, str]:
        return {"status": "ok", "redis": app.state.kv.probe()}

    enabled = settings.biometrics_enabled
    app.add_middleware(BodyLimitMiddleware, limit=lambda path: limit_for(path, enabled))
    app.add_middleware(SecurityHeadersMiddleware)
    return app

