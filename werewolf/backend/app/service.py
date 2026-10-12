"""Glue between the store, the hub and persistence. Used by both REST routes and the socket."""

import asyncio
import logging
from typing import Callable

from anyio import from_thread
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app.engine import Game
from app.history import save_result
from app.store import UpdateResult

logger = logging.getLogger(__name__)
REAPER_INTERVAL_SECONDS = 60.0


def _save(app: FastAPI, room_id: str, game: Game) -> None:
    """Write the result; only a successful write marks the room as persisted (else it is retried)."""
    if save_result(app.state.session_factory, room_id, game):
        app.state.store.mark_persisted(room_id)


def apply_sync(app: FastAPI, room_id: str, transition: Callable[[Game], Game]) -> Game:
    """For plain `def` route handlers (they run in a worker thread)."""
    result = app.state.store.update(room_id, transition)
    if result.finished_now:
        _save(app, room_id, result.game)
    from_thread.run(app.state.hub.broadcast_state, room_id, result.game)
    return result.game


async def apply_async(app: FastAPI, room_id: str, transition: Callable[[Game], Game]) -> Game:
    """For the async WebSocket handler: the store is quick, only the DB write is offloaded."""
    result: UpdateResult = app.state.store.update(room_id, transition)
    if result.finished_now:
        await run_in_threadpool(_save, app, room_id, result.game)
    await app.state.hub.broadcast_state(room_id, result.game)
    return result.game


def sweep(app: FastAPI) -> None:
    """One reaper pass: retry unsaved results, then delete expired rooms."""
    for room_id, game in app.state.store.unsaved_results():
        _save(app, room_id, game)
    app.state.store.reap()


async def reaper_loop(app: FastAPI, interval: float = REAPER_INTERVAL_SECONDS) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await run_in_threadpool(sweep, app)
        except Exception:
            logger.exception("Room reaper pass failed")
