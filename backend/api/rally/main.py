import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from api.rally.db import Base, make_engine
from api.rally.routes import router
from sn_shared import directory
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.deps import access_dependencies
from sn_shared.jwtkeys import require_verification_keys
from sn_shared.limits import UserRateLimiter

import logging
logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "sqlite:///./rally.db"
READS_PER_MINUTE = 240


def create_app(database_url: str | None = None) -> FastAPI:
    try:
        require_verification_keys()
        engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        Base.metadata.create_all(engine)
        directory.ensure_table_for_sqlite(engine)  # sqlite only: the users table the tests and the local run read from

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            handle = start_consumer("rally", application.state.session_factory)
            try:
                yield
            finally:
                if handle is not None:
                    await stop_consumer(handle)

        app = FastAPI(title="socialnetwork rally", lifespan=lifespan)
        app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
        app.state.limiter = UserRateLimiter()
        app.state.read_limiter = UserRateLimiter(max_events=READS_PER_MINUTE)

        @app.get("/health", dependencies=access_dependencies(public=True))
        def health() -> dict[str, str]:
            try:
                return {"status": "ok"}
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("health failed")
                raise

        app.include_router(router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        return app
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_app failed")
        raise
