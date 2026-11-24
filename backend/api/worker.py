"""The worker of the backend: `python -m api.worker` (the same image as the API, another command).

A module that has work for a queue adds `(QueueSpec, handler)` to CONSUMERS (see `sn_shared.messaging`); the worker keeps one consumer per
entry and reconnects when the broker goes away. With no consumer declared it only waits, so the service can stay in the compose file.
"""

import asyncio
import contextlib
import logging
import os
import signal
from pathlib import Path

from sn_shared.messaging import Handler, QueueSpec, consume

log = logging.getLogger("api.worker")

# (queue, handler) of every module that consumes a queue.
CONSUMERS: list[tuple[QueueSpec, Handler]] = []

ALIVE_FILE = Path(os.environ.get("WORKER_ALIVE_FILE", "/tmp/worker-alive"))
RECONNECT_SECONDS = 3.0
HEARTBEAT_SECONDS = 20.0


async def _keep_consuming(spec: QueueSpec, handler: Handler, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await consume(spec, handler, stop)
        except Exception as exc:
            log.warning("queue %s: %s; trying again in %.0f s", spec.name, exc, RECONNECT_SECONDS)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), RECONNECT_SECONDS)


async def _heartbeat(stop: asyncio.Event) -> None:
    while not stop.is_set():
        with contextlib.suppress(OSError):
            ALIVE_FILE.touch()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), HEARTBEAT_SECONDS)


async def run(consumers: list[tuple[QueueSpec, Handler]] | None = None, stop: asyncio.Event | None = None) -> None:
    stop = stop or asyncio.Event()
    entries = CONSUMERS if consumers is None else consumers
    await asyncio.gather(_heartbeat(stop), *(_keep_consuming(spec, handler, stop) for spec, handler in entries))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stop = asyncio.Event()

    async def go() -> None:
        loop = asyncio.get_running_loop()
        for name in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(name, stop.set)
        await run(stop=stop)

    asyncio.run(go())


if __name__ == "__main__":
    main()
