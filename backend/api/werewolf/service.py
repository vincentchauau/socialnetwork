"""Glue between the store, the hub and persistence. Used by both the REST routes and the WebSocket."""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from api.werewolf import chat_remote, snapshots
from api.werewolf.history import save_record
from api.werewolf.rooms import GameRecord, Room
from api.werewolf.store import MAX_PERSIST_ATTEMPTS

logger = logging.getLogger(__name__)
REAPER_INTERVAL_SECONDS = 60.0
TICK_SECONDS = 1.0


async def store_record(app: FastAPI, record: GameRecord) -> None:
    """Write one result in a worker thread; only a successful write marks it saved (else it is retried)."""
    if record.saved or record.inflight:
        return
    record.inflight = True
    record.attempts += 1
    try:
        record.saved = await run_in_threadpool(save_record, app.state.session_factory, record)
    finally:
        record.inflight = False


async def announce(app: FastAPI, record: GameRecord) -> None:
    """Tell the chat, once, that the game is over (it says so in the room, if the game is of a room of the chat)."""
    if record.announced:
        return
    record.announced = True  # (a failed call is not repeated: it is only a line of the conversation)
    await run_in_threadpool(chat_remote.game_over, app, record)


async def persist(app: FastAPI, room: Room) -> None:
    room.collect_result()
    for record in list(room.records):
        await announce(app, record)
        if record.attempts < MAX_PERSIST_ATTEMPTS:
            await store_record(app, record)
    room.records[:] = [r for r in room.records if not r.saved]


async def commit(app: FastAPI, room: Room) -> None:
    """After any change to a room: store a finished game once, then push every connected user their own view."""
    await persist(app, room)
    await snapshots.save(app, room)  # a restart puts the room back as it is now
    await app.state.ww_hub.broadcast(room.code, lambda uid: room.state_for(uid) if room.seat_index(uid) is not None else None)


async def save_pending(app: FastAPI) -> None:
    """Store (or retry) every result that is still unsaved, including those of rooms already deleted."""
    for record in app.state.ww_store.unsaved_results():
        await announce(app, record)
        await store_record(app, record)


async def sweep(app: FastAPI) -> None:
    """One reaper pass: retry unsaved results, then delete expired rooms."""
    await save_pending(app)
    app.state.ww_store.reap()
    await snapshots.save(app)  # forget the copies of rooms that are gone


async def tick_once(app: FastAPI) -> int:
    """Run every expired turn timer of rooms somebody is connected to; returns how many rooms advanced."""
    advanced = 0
    for room in app.state.ww_store.all():
        if room.game is None or room.game.game_over or app.state.ww_hub.size(room.code) == 0:
            continue
        if room.tick():
            advanced += 1
            await commit(app, room)
    return advanced


async def forever_service(app: FastAPI, interval: float, step) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await step(app)
        except Exception:
            logger.exception("Background step %s failed", step.__name__)


async def reaper_loop(app: FastAPI, interval: float = REAPER_INTERVAL_SECONDS) -> None:
    await forever_service(app, interval, sweep)


async def tick_loop(app: FastAPI, interval: float = TICK_SECONDS) -> None:
    await forever_service(app, interval, tick_once)
