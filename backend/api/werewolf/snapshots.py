"""Games that survive a restart: every room is saved after each change and put back when the server starts.

A room (its seats, its game with the night, the votes, the roles) is pickled into one live row of `games`. Only the clock cannot be
kept (monotonic time starts again at every boot): it is taken off before saving and given back on loading, and the timer of the
turn that was running starts again, which is fair to everybody. The bytes come from this database only, and are still read with
an unpickler that knows nothing but the classes of the game, so a changed row cannot run anything.

Saving is best effort and never breaks a game: a failure is logged and the next change tries again. Rooms that were deleted
(`store.removed`) have their row deleted at the next change or sweep.
"""

import io
import logging
import os
import pickle
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from api.werewolf.models import LIVE, Game
from api.werewolf.rooms import Room

log = logging.getLogger(__name__)

_ALLOWED_MODULES = ("api.werewolf.",)
_ALLOWED_NAMES = {
    ("random", "Random"),
    ("builtins", "set"),
    ("builtins", "frozenset"),
    ("builtins", "complex"),
    ("collections", "OrderedDict"),
    ("collections", "deque"),
    ("collections", "defaultdict"),
    ("copyreg", "_reconstructor"),
    ("builtins", "object"),
}


class _GameUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if module.startswith("app.werewolf."):  # a room saved before the modules were put in one package
            module = "api." + module[len("app."):]
        if module.startswith("api.chat.werewolf."):  # a room saved while the game was a part of the chat
            module = "api.werewolf." + module[len("api.chat.werewolf."):]
        if module.startswith(_ALLOWED_MODULES) or (module, name) in _ALLOWED_NAMES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"{module}.{name} is not part of a game")


SEALED = b"gAAAA"  # how a Fernet token begins


def _fernet():
    """The key that seals the rows (`WEREWOLF_SNAPSHOT_KEY`, a Fernet key), or None: a saved room holds every role and every secret
    action of a game that is still running, so with a key nobody who reads the database reads them."""
    key = os.environ.get("WEREWOLF_SNAPSHOT_KEY", "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode())


def dump(room: Room) -> bytes:
    """The bytes of a room, without its clock (given back, unchanged, afterwards), sealed when there is a key."""
    game = room.game
    clock, game_clock = room.clock, (game._clock if game is not None else None)
    room.clock = None  # type: ignore[assignment]
    if game is not None:
        game._clock = None  # type: ignore[assignment]
    try:
        data = pickle.dumps(room, protocol=pickle.HIGHEST_PROTOCOL)
        sealer = _fernet()
        return sealer.encrypt(data) if sealer is not None else data
    finally:
        room.clock = clock
        if game is not None:
            game._clock = game_clock  # type: ignore[assignment]


def load(data: bytes, clock: Callable[[], float]) -> Room:
    """A room from its bytes, on the clock of this boot. Raises when the bytes are not a room (or are sealed and there is no key)."""
    if data.startswith(SEALED):
        sealer = _fernet()
        if sealer is None:
            raise pickle.UnpicklingError("the room is sealed and there is no key")
        data = sealer.decrypt(data)  # raises when the key is not the one that sealed it
    room = _GameUnpickler(io.BytesIO(data)).load()
    if not isinstance(room, Room):
        raise pickle.UnpicklingError("not a room")
    room.clock = clock
    if room.game is not None:
        room.game._clock = clock
        room.game._timer_key = None  # the turn that was running starts its time again
    room.last_active = clock()
    return room


def _write(factory: sessionmaker, rows: dict[str, bytes], removed: set[str]) -> None:
    with factory() as db:
        for code, data in rows.items():
            live = db.scalar(select(Game).where(Game.room_code == code, Game.status == LIVE))
            if live is None:
                db.add(Game(room_code=code, status=LIVE, state=data))
            else:
                live.state = data
        if removed:
            db.execute(delete(Game).where(Game.room_code.in_(removed), Game.status == LIVE))  # (the results of its games stay)
        db.commit()


async def save(app: FastAPI, *rooms: Room) -> None:
    """Keep these rooms (and forget the deleted ones). Never raises."""
    store = app.state.ww_store
    removed, store.removed = set(store.removed), set()
    try:
        rows = {room.code: dump(room) for room in rooms}
        if rows or removed:
            await run_in_threadpool(_write, app.state.session_factory, rows, removed)
    except Exception:  # noqa: BLE001 - a game must go on when its copy could not be kept
        store.removed |= removed
        log.exception("could not keep the werewolf rooms")


async def restore(app: FastAPI) -> int:
    """Put back every saved room that is still good; returns how many. A row that cannot be read is dropped."""
    store = app.state.ww_store

    def read() -> list[tuple[str, bytes]]:
        with app.state.session_factory() as db:
            return [(row.room_code, row.state) for row in db.scalars(select(Game).where(Game.status == LIVE, Game.state.is_not(None)))]

    put = 0
    bad: set[str] = set()
    for code, data in await run_in_threadpool(read):
        try:
            room = load(data, store.clock)
        except Exception:  # noqa: BLE001 - a row from an older version, or damaged
            log.warning("a saved werewolf room (%s) could not be read and was dropped", code)
            bad.add(code)
            continue
        if room.code == code and code not in store.codes():
            store.adopt(room)
            put += 1
    if bad:
        await run_in_threadpool(_write, app.state.session_factory, {}, bad)
    return put
