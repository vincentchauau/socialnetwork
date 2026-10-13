import asyncio

import fakeredis
import pytest

from app.adapters.cache import RedisCache
from app.adapters.users import GrpcUserDirectory
from app.interfaces import Unavailable
from app.user_server import build_server


def run(coro):
    return asyncio.run(coro)


def test_redis_cache_roundtrip_and_ttl():
    async def go():
        client = fakeredis.FakeAsyncRedis(decode_responses=True)
        cache = RedisCache(client=client)
        assert await cache.ping() is True
        assert await cache.get("k") is None
        await cache.set("k", "v", 300)
        assert await cache.get("k") == "v"
        assert 0 < await client.ttl("k") <= 300
        await cache.delete("k")
        assert await cache.get("k") is None
        await cache.close()

    run(go())


def test_redis_cache_maps_errors_to_unavailable():
    class Broken:
        async def get(self, *a, **k):
            raise ConnectionError

        set = delete = ping = get

        async def aclose(self):
            raise ConnectionError

    async def go():
        cache = RedisCache(client=Broken())
        with pytest.raises(Unavailable):
            await cache.get("k")
        with pytest.raises(Unavailable):
            await cache.set("k", "v", 1)
        with pytest.raises(Unavailable):
            await cache.delete("k")
        assert await cache.ping() is False
        await cache.close()  # swallowed

    run(go())


def test_redis_cache_builds_a_client_from_url():
    async def go():
        cache = RedisCache("redis://127.0.0.1:1/0")
        assert await cache.ping() is False
        await cache.close()

    run(go())


def test_grpc_user_server_and_client_end_to_end():
    async def go():
        server, port = build_server("127.0.0.1:0")
        await server.start()
        users = GrpcUserDirectory(f"127.0.0.1:{port}")
        try:
            assert await users.get_user("1") == "Alice"
            assert await users.get_user("2") == "Bob"
            assert await users.get_user("3") == "Charlie"
            assert await users.get_user("42") == "Unknown"
            assert await users.ping() is True
        finally:
            await server.stop(None)
        with pytest.raises(Unavailable):
            await users.get_user("1", timeout=0.5)
        assert await users.ping() is False
        await users.close()

    run(go())
