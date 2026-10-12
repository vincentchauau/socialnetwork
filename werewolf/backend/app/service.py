"""Glue between the store, the hub and persistence. Used by both REST routes and the socket."""

from typing import Callable

from anyio import from_thread
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from app.engine import Game
from app.history import save_result
from app.store import UpdateResult


def apply_sync(app: FastAPI, room_id: str, transition: Callable[[Game], Game]) -> Game:
    """For plain `def` route handlers (they run in a worker thread)."""
    result = app.state.store.update(room_id, transition)
    if result.finished_now:
        save_result(app.state.session_factory, room_id, result.game)
    from_thread.run(app.state.hub.broadcast_state, room_id, result.game)
    return result.game


async def apply_async(app: FastAPI, room_id: str, transition: Callable[[Game], Game]) -> Game:
    """For the async WebSocket handler: the store is quick, only the DB write is offloaded."""
    result: UpdateResult = app.state.store.update(room_id, transition)
    if result.finished_now:
        await run_in_threadpool(save_result, app.state.session_factory, room_id, result.game)
    await app.state.hub.broadcast_state(room_id, result.game)
    return result.game
