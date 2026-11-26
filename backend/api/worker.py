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

logger = logging.getLogger(__name__)

log = logging.getLogger("api.worker")

# (queue, handler) of every module that consumes a queue.
CONSUMERS: list[tuple[QueueSpec, Handler]] = []

ALIVE_FILE = Path(os.environ.get("WORKER_ALIVE_FILE", "/tmp/worker-alive"))
RECONNECT_SECONDS = 3.0
HEARTBEAT_SECONDS = 20.0


async def keep_consuming(spec: QueueSpec, handler: Handler, stop: asyncio.Event) -> None:
    try:
        while not stop.is_set():
            try:
                await consume(spec, handler, stop)
            except Exception as exc:
                log.warning("queue %s: %s; trying again in %.0f s", spec.name, exc, RECONNECT_SECONDS)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), RECONNECT_SECONDS)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("keep_consuming failed")
        raise


async def heartbeat(stop: asyncio.Event) -> None:
    try:
        while not stop.is_set():
            with contextlib.suppress(OSError):
                ALIVE_FILE.touch()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), HEARTBEAT_SECONDS)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("heartbeat failed")
        raise


async def run(consumers: list[tuple[QueueSpec, Handler]] | None = None, stop: asyncio.Event | None = None) -> None:
    try:
        stop = stop or asyncio.Event()
        entries = CONSUMERS if consumers is None else consumers
        await asyncio.gather(heartbeat(stop), *(keep_consuming(spec, handler, stop) for spec, handler in entries))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("run failed")
        raise


def main() -> None:
    try:
        logging.basicConfig(level=logging.INFO)
        stop = asyncio.Event()

        async def go() -> None:
            try:
                loop = asyncio.get_running_loop()
                for name in (signal.SIGINT, signal.SIGTERM):
                    with contextlib.suppress(NotImplementedError):
                        loop.add_signal_handler(name, stop.set)
                await run(stop=stop)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("go failed")
                raise

        asyncio.run(go())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("main failed")
        raise


if __name__ == "__main__":
    main()
