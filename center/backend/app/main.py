import os
import threading

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app.bodylimit import BodyLimitMiddleware, limit_for
from app.config import Settings
from app.crypto import TemplateCipher
from app.db import DEFAULT_DATABASE_URL, Base, make_engine
from app.google_auth import make_google_verifier
from app.middleware import SecurityHeadersMiddleware
from app.migrate import ensure_columns
from app.routes_account import router as account_router
from app.routes_auth import router as auth_router
from app.routes_biometrics import router as biometrics_router
from app.routes_methods import combined_router, methods_router
from app.throttle import AttemptThrottle

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
WEBCAM_ACCOUNT_MAX_FAILURES = 5  # identified face but wrong voice: locks that account's webcam sign-in
ENROLL_MAX_PER_HOUR = 10
MAX_CONCURRENT_BIOMETRICS = 2


def _install_throttles(app: FastAPI) -> None:
    state = app.state
    state.login_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_IP_USER)
    state.login_ip_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_IP)
    state.login_account_throttle = AttemptThrottle(
        max_attempts=LOGIN_MAX_FAILURES_PER_IP_USER * LOGIN_ACCOUNT_FACTOR
    )
    state.register_throttle = AttemptThrottle(
        max_attempts=REGISTER_MAX_PER_IP, window_seconds=REGISTER_WINDOW_SECONDS
    )
    state.refresh_throttle = AttemptThrottle(
        max_attempts=REFRESH_MAX_PER_IP, window_seconds=REFRESH_WINDOW_SECONDS
    )
    state.reauth_throttle = AttemptThrottle(max_attempts=REAUTH_MAX_FAILURES)
    window = BIOMETRIC_WINDOW_SECONDS
    state.bio_throttle = AttemptThrottle(BIOMETRIC_MAX_FAILURES, window)
    state.bio_account_throttle = AttemptThrottle(BIOMETRIC_MAX_FAILURES * BIOMETRIC_ACCOUNT_FACTOR, window)
    state.alone_throttle = AttemptThrottle(BIOMETRIC_ONLY_MAX_ATTEMPTS, window)
    state.alone_account_throttle = AttemptThrottle(BIOMETRIC_ONLY_MAX_ATTEMPTS * BIOMETRIC_ACCOUNT_FACTOR, window)
    state.identify_ip_throttle = AttemptThrottle(IDENTIFY_MAX_PER_IP, window)
    state.identify_global_throttle = AttemptThrottle(IDENTIFY_GLOBAL_MAX, window)
    state.webcam_account_throttle = AttemptThrottle(WEBCAM_ACCOUNT_MAX_FAILURES, window)
    state.enroll_throttle = AttemptThrottle(ENROLL_MAX_PER_HOUR, 3600.0)
    state.biometric_slots = threading.BoundedSemaphore(MAX_CONCURRENT_BIOMETRICS)


def _install_biometrics(app: FastAPI, settings: Settings) -> None:
    app.state.biometrics = None
    app.state.cipher = None
    if settings.biometrics_enabled:
        from app.biometrics import RealBiometrics  # heavy libraries load lazily inside

        app.state.cipher = TemplateCipher(settings.data_key)  # fails at startup on a bad key
        app.state.biometrics = RealBiometrics(settings)


def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", ())[1:])
    message = str(first.get("msg", "Invalid request")).removeprefix("Value error, ")
    return JSONResponse({"detail": f"{field}: {message}" if field else message}, status_code=422)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = Settings.from_env()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)
    ensure_columns(engine)  # upgrade a users table created by an older version

    docs = None if settings.production else "/docs"
    app = FastAPI(
        title="socialnetwork center",
        docs_url=docs,
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    _install_throttles(app)
    _install_biometrics(app, settings)
    app.state.google_verifier = (
        make_google_verifier(settings.google_client_id) if settings.google_client_id else None
    )
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(biometrics_router)
    app.include_router(methods_router)
    app.include_router(combined_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    enabled = settings.biometrics_enabled
    app.add_middleware(BodyLimitMiddleware, limit=lambda path: limit_for(path, enabled))
    app.add_middleware(SecurityHeadersMiddleware)
    return app


app = create_app()
