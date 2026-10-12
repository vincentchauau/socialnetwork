import asyncio
import inspect
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import routes, ws
from app.db import Base, make_engine
from app.hub import GameHub
from app.service import reaper_loop
from app.store import RoomStore
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./werewolf.db"


def _start_account_consumer(session_factory: sessionmaker) -> Any:
    """Start center's account-event consumer; None in tests, without Redis or without the library."""
    if os.environ.get("TESTING") or not os.environ.get("REDIS_URL"):
        return None
    try:
        from sn_shared.events import start_account_consumer
    except ImportError:
        return None
    return start_account_consumer("werewolf", session_factory)


async def _stop_account_consumer(handle: Any) -> None:
    stop = getattr(handle, "stop", None) or getattr(handle, "close", None)
    if stop is None:
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


def create_app(database_url: str | None = None) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        reaper = asyncio.create_task(reaper_loop(application))
        handle = _start_account_consumer(application.state.session_factory)
        try:
            yield
        finally:
            if handle is not None:
                await _stop_account_consumer(handle)
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
