from sn_shared.deps import access_dependencies
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from api.face import measurements
from api.face.db import Base, ensure_columns, make_engine
from sn_shared.limits import UserRateLimiter
from api.face import admin as admin_routes
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./face.db"


stop_account_consumer = stop_consumer


def create_app(database_url: str | None = None) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)
    ensure_columns(engine, "measurements", {"note": "VARCHAR(200) NOT NULL DEFAULT ''"})  # added after the table was first made

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        handle = start_consumer("face", application.state.session_factory)
        try:
            yield
        finally:
            if handle is not None:
                await stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork face", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.limiter = UserRateLimiter(max_events=30)

    @app.get("/health", dependencies=access_dependencies(public=True))
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(measurements.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    admin_routes.mount(app)
    return app

