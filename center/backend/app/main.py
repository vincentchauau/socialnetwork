import os

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.db import Base, make_engine
from app.routes_auth import router as auth_router
from app.throttle import AttemptThrottle
from sn_shared.security import get_jwt_secret

DEFAULT_DATABASE_URL = "sqlite:///./center.db"
LOGIN_MAX_FAILURES_PER_ACCOUNT = 5  # per (client address, username)
LOGIN_MAX_FAILURES_PER_IP = 20  # across all usernames from one address
REGISTER_MAX_PER_IP = 10
REGISTER_WINDOW_SECONDS = 600.0


def create_app(database_url: str | None = None) -> FastAPI:
    get_jwt_secret()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    app = FastAPI(title="socialnetwork center")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.login_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_ACCOUNT)
    app.state.login_ip_throttle = AttemptThrottle(max_attempts=LOGIN_MAX_FAILURES_PER_IP)
    app.state.register_throttle = AttemptThrottle(
        max_attempts=REGISTER_MAX_PER_IP, window_seconds=REGISTER_WINDOW_SECONDS
    )
    app.include_router(auth_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
