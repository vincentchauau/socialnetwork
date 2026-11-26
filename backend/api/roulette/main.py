from sn_shared.deps import access_dependencies
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from api.roulette import play
from api.roulette.models import Spin, Wallet
from api.roulette.db import Base, make_engine
from sn_shared import directory
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys
from sn_shared.limits import UserRateLimiter

import logging
logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "sqlite:///./roulette.db"
READS_PER_MINUTE = 240


stop_account_consumer = stop_consumer


def create_app(database_url: str | None = None) -> FastAPI:
    try:
        require_verification_keys()
        engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        Base.metadata.create_all(engine)
        directory.ensure_table_for_sqlite(engine)  # names are read from center's `users`

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            handle = start_consumer("roulette", application.state.session_factory)
            try:
                yield
            finally:
                if handle is not None:
                    await stop_account_consumer(handle)

        app = FastAPI(title="socialnetwork roulette", lifespan=lifespan)
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

        app.include_router(play.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        specs = [TableSpec(Spin, owner="user_id", readonly_columns=("user_id",)), TableSpec(Wallet, owner="user_id", groups=("admin",))]
        mount_crud(app, specs, database="roulette")
        return app
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_app failed")
        raise
