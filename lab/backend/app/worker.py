"""lab-worker: ONE process, two asyncio consumers (RabbitMQ notifications, Kafka log writer).

    python -m app.worker

Each consumer is supervised: if its broker is down or drops, it is retried every few seconds, so the worker
can be started before the brokers are healthy and survives their restarts. Message bodies are never logged.
"""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.db import Base, make_engine
from app.processing import LogWriter, NotificationProcessor

log = logging.getLogger("lab.worker")

RETRY_DELAY_SECONDS = 5.0
HEARTBEAT_SECONDS = 10.0
HEARTBEAT_FILE = Path(os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/worker-alive"))  # noqa: S108


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), seconds)


async def supervise(
    name: str, run: Callable[[], Awaitable[None]], stop: asyncio.Event, retry_delay: float = RETRY_DELAY_SECONDS
) -> None:
    """Run `run` until `stop` is set, restarting it after any failure."""
    while not stop.is_set():
        try:
            await run()
        except Exception as exc:
            log.warning("%s consumer stopped (%s); retrying in %.0fs", name, type(exc).__name__, retry_delay)
            await _wait(stop, retry_delay)


async def heartbeat(path: Path, stop: asyncio.Event, interval: float = HEARTBEAT_SECONDS) -> None:
    """Touch `path` while the event loop is alive (the container healthcheck looks at its age)."""
    while not stop.is_set():
        with contextlib.suppress(OSError):
            path.touch()
        await _wait(stop, interval)


async def run_worker(
    factory: sessionmaker,
    stop: asyncio.Event,
    notifications: Callable[[Callable[[bytes], Awaitable[str]], asyncio.Event], Awaitable[None]],
    logs: Callable[[Callable[..., Awaitable[object]], asyncio.Event], Awaitable[None]],
    heartbeat_file: Path = HEARTBEAT_FILE,
    retry_delay: float = RETRY_DELAY_SECONDS,
) -> None:
    processor = NotificationProcessor(factory)
    writer = LogWriter(factory)
    await asyncio.gather(
        supervise("rabbitmq", lambda: notifications(processor.handle, stop), stop, retry_delay),
        supervise("kafka", lambda: logs(writer.handle, stop), stop, retry_delay),
        heartbeat(heartbeat_file, stop),
    )


async def main() -> None:  # pragma: no cover - process entry point
    from app.adapters.amqp import consume_notifications
    from app.adapters.kafka import consume_logs

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    engine = make_engine(os.environ["DATABASE_URL"])
    Base.metadata.create_all(engine)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    await run_worker(sessionmaker(engine, expire_on_commit=False), stop, consume_notifications, consume_logs)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
