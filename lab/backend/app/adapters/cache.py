"""Redis cache (redis.asyncio)."""

from redis import asyncio as aioredis

from app.interfaces import Unavailable


class RedisCache:
    def __init__(self, url: str | None = None, client: aioredis.Redis | None = None) -> None:
        if client is None:
            client = aioredis.from_url(
                url or "redis://redis:6379/0", socket_timeout=1.0, socket_connect_timeout=1.0, decode_responses=True
            )
        self._client = client

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except Exception as exc:
            raise Unavailable("redis") from exc

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._client.set(key, value, ex=ttl_seconds)
        except Exception as exc:
            raise Unavailable("redis") from exc

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as exc:
            raise Unavailable("redis") from exc

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass
