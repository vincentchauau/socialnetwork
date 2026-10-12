import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import routes, ws
from app.db import Base, make_engine
from app.hub import GameHub
from app.service import reaper_loop
from app.store import RoomStore
from sn_shared.security import get_jwt_secret

DEFAULT_DATABASE_URL = "sqlite:///./werewolf.db"


def create_app(database_url: str | None = None) -> FastAPI:
    get_jwt_secret()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        reaper = asyncio.create_task(reaper_loop(application))
        try:
            yield
        finally:
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper

    app = FastAPI(title="socialnetwork werewolf", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.hub = GameHub()
    app.state.store = RoomStore(is_connected=lambda room_id: app.state.hub.size(room_id) > 0)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


app = create_app()
