import asyncio

from app.rooms import MessageRateLimiter, RoomHub


class FakeSocket:
    def __init__(self, delay: float = 0.0, fail: bool = False) -> None:
        self.delay = delay
        self.fail = fail
        self.accepted = False
        self.received: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("socket closed")
        await asyncio.sleep(self.delay)
        self.received.append(payload)


def run(coro):
    return asyncio.run(coro)


def test_broadcast_reaches_every_socket_in_room():
    async def scenario():
        hub = RoomHub()
        first, second = FakeSocket(), FakeSocket()
        await hub.join("r", first)
        await hub.join("r", second)
        await hub.broadcast("r", {"n": 1})
        return first.received, second.received

    first, second = run(scenario())
    assert first == second == [{"n": 1}]


def test_slow_socket_does_not_block_others_and_is_dropped():
    async def scenario():
        hub = RoomHub(send_timeout=0.05)
        slow, fast = FakeSocket(delay=1.0), FakeSocket()
        await hub.join("r", slow)
        await hub.join("r", fast)
        await hub.broadcast("r", {"n": 1})
        await hub.broadcast("r", {"n": 2})
        return fast.received, slow.received, hub.size("r")

    fast, slow, size = run(scenario())
    assert fast == [{"n": 1}, {"n": 2}]
    assert slow == []
    assert size == 1


def test_failing_socket_is_dropped():
    async def scenario():
        hub = RoomHub()
        broken, healthy = FakeSocket(fail=True), FakeSocket()
        await hub.join("r", broken)
        await hub.join("r", healthy)
        await hub.broadcast("r", {"n": 1})
        return healthy.received, hub.size("r")

    received, size = run(scenario())
    assert received == [{"n": 1}]
    assert size == 1


def test_leave_removes_empty_room():
    async def scenario():
        hub = RoomHub()
        socket = FakeSocket()
        await hub.join("r", socket)
        hub.leave("r", socket)
        hub.leave("r", socket)  # leaving twice is harmless
        return hub.size("r")

    assert run(scenario()) == 0


def test_rate_limiter_allows_burst_then_blocks_and_recovers():
    clock = [0.0]
    limiter = MessageRateLimiter(max_events=3, window_seconds=10, now=lambda: clock[0])

    assert [limiter.allow() for _ in range(4)] == [True, True, True, False]
    clock[0] = 11.0
    assert limiter.allow()
