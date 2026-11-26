from sn_shared.deps import access_dependencies
import asyncio
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI
from sqlalchemy import and_
from sqlalchemy.orm import sessionmaker

from api import werewolf as game
from api.werewolf.db import Base, make_engine
from api.werewolf.models import FINISHED, Game
from api.werewolf.internal import router as internal_router
from api.werewolf.migrate import merge_legacy_tables
from sn_shared import directory
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./werewolf.db"


_stop_account_consumer = stop_consumer


def _played_finished_game(db, user):
    return and_(Game.status == FINISHED, Game.player_ids.like(f"%|{int(user.user_id)}|%"))


def create_app(database_url: str | None = None, clock: Callable[[], float] = time.monotonic) -> FastAPI:
    require_verification_keys()
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)
    directory.ensure_table_for_sqlite(engine)  # names are read from `users` of center (SQLite has none: an empty one)
    game.ensure_columns(engine)  # databases made by the old 4-role game get the new result columns
    merge_legacy_tables(engine)  # the three tables of before are one (`games`): their rows are copied, once

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        handle = start_consumer("werewolf", application.state.session_factory)
        await game.restore(application)  # the games that were running before a restart
        games = [asyncio.create_task(game.reaper_loop(application)), asyncio.create_task(game.tick_loop(application))]
        try:
            yield
        finally:
            for task in games:
                task.cancel()
            for task in games:
                with suppress(asyncio.CancelledError):
                    await task
            if handle is not None:
                await _stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork werewolf", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    # The games (rooms live in memory; only the results are stored): their hub, limits and store.
    app.state.ww_hub = game.GameHub()
    app.state.ww_limits = game.UserLimits(clock)
    app.state.ww_store = game.RoomStore(clock=clock, is_connected=lambda code: app.state.ww_hub.size(code) > 0)

    @app.get("/health", dependencies=access_dependencies(public=True))
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(game.router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(game.ws_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    app.include_router(internal_router, dependencies=access_dependencies(public=True))
    # `state` (LargeBinary) is always masked and not writable: it holds every role and secret action of a live game.
    # /data: a person reads only the finished games they played (never `state`).
    specs = [TableSpec(Game, secret_columns=("state",), scope=_played_finished_game, user_hidden_columns=("state",))]
    mount_crud(app, specs, database="werewolf")
    return app
