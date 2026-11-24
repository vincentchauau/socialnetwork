"""The worker with nothing to consume: it beats, and stops when told."""

import asyncio

from api import worker


def test_the_worker_with_no_consumer_beats_and_stops(tmp_path, monkeypatch):
    alive = tmp_path / "alive"
    monkeypatch.setattr(worker, "ALIVE_FILE", alive)

    async def go() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run(consumers=[], stop=stop))
        await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(task, 3)

    asyncio.run(go())
    assert alive.exists()
