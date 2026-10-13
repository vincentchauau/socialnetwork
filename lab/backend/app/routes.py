"""The /api/lab routes. All errors are {"detail": "<Vietnamese message>"}."""

import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app import repo
from app.interfaces import (
    PROBE_TIMEOUT_SECONDS,
    USER_CACHE_PREFIX,
    USER_CACHE_TTL_SECONDS,
    Services,
    Unavailable,
)
from app.processing import replay_message
from app.schemas import LogIn, NotificationIn
from app.security import check_origin
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

USER_ID_PATTERN = r"^[0-9A-Za-z]{1,16}$"
MSG_TOO_MANY = "Bạn thao tác quá nhanh, hãy thử lại sau ít phút."
MSG_GRPC_DOWN = "Dịch vụ người dùng (gRPC) chưa sẵn sàng."
MSG_RABBIT_DOWN = "RabbitMQ chưa chạy. Hãy bật profile messaging."
MSG_KAFKA_DOWN = "Kafka chưa chạy. Hãy bật profile messaging."


def services(request: Request) -> Services:
    return request.app.state.services


def write_limited(request: Request, user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Authenticated + at most 30 writes per minute per user (POSTs and DELETEs)."""
    if not request.app.state.limiter.allow(user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, MSG_TOO_MANY)
    return user


def _factory(request: Request):
    return request.app.state.session_factory


async def _probe(check) -> bool:
    try:
        return bool(await asyncio.wait_for(check(), PROBE_TIMEOUT_SECONDS))
    except Exception:
        return False


@router.get("/status")
async def get_status(
    _: TokenPayload = Depends(get_current_user), svc: Services = Depends(services)
) -> dict[str, bool]:
    redis, grpc, rabbitmq, kafka = await asyncio.gather(
        _probe(svc.cache.ping), _probe(svc.users.ping), _probe(svc.queue.ping), _probe(svc.logs.ping)
    )
    return {"redis": redis, "grpc": grpc, "rabbitmq": rabbitmq, "kafka": kafka, "messaging": rabbitmq and kafka}


# --- gRPC + Redis cache-aside -------------------------------------------------------------------------------


@router.get("/users/{user_id}")
async def get_user(
    user_id: Annotated[str, Path(pattern=USER_ID_PATTERN)],
    _: TokenPayload = Depends(get_current_user),
    svc: Services = Depends(services),
) -> dict:
    started = time.perf_counter()
    key = USER_CACHE_PREFIX + user_id
    name, source = await _cached_name(svc, key)
    if name is None:
        try:
            name = await svc.users.get_user(user_id)
        except Unavailable:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_GRPC_DOWN) from None
        source = "grpc"
        try:
            await svc.cache.set(key, json.dumps({"name": name}), USER_CACHE_TTL_SECONDS)
        except Unavailable:
            pass  # a cache that is down only costs speed
    return {"id": user_id, "name": name, "source": source, "ms": round((time.perf_counter() - started) * 1000)}


async def _cached_name(svc: Services, key: str) -> tuple[str | None, str]:
    try:
        raw = await svc.cache.get(key)
        if raw is not None:
            return json.loads(raw)["name"], "cache"
    except (Unavailable, ValueError, KeyError, TypeError):
        pass  # unreachable or unreadable entry: treat as a miss
    return None, "grpc"


@router.delete(
    "/users/{user_id}/cache", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(check_origin)]
)
async def clear_user_cache(
    user_id: Annotated[str, Path(pattern=USER_ID_PATTERN)],
    _: TokenPayload = Depends(write_limited),
    svc: Services = Depends(services),
) -> Response:
    try:
        await svc.cache.delete(USER_CACHE_PREFIX + user_id)
    except Unavailable:
        pass  # nothing cached if Redis is down
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- RabbitMQ work queue ------------------------------------------------------------------------------------


@router.post(
    "/notifications",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(check_origin)],
)
async def create_notification(
    body: NotificationIn,
    request: Request,
    user: TokenPayload = Depends(write_limited),
    svc: Services = Depends(services),
) -> dict[str, int]:
    factory = _factory(request)
    event_id = await run_in_threadpool(repo.create_notification, factory, user.user_id, body.title, body.body)
    payload = json.dumps({"id": event_id, "userId": user.user_id, "title": body.title, "body": body.body})
    try:
        await svc.queue.publish(payload.encode())
    except Unavailable:
        await run_in_threadpool(repo.remove_event, factory, event_id)  # nothing stays stored
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_RABBIT_DOWN) from None
    return {"id": event_id}


@router.get("/notifications")
async def list_notifications(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    user: TokenPayload = Depends(get_current_user),
) -> list[dict]:
    return await run_in_threadpool(repo.list_notifications, _factory(request), user.user_id, limit)


# --- Kafka event log ----------------------------------------------------------------------------------------


@router.post("/logs", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(check_origin)])
async def create_log(
    body: LogIn,
    user: TokenPayload = Depends(write_limited),
    svc: Services = Depends(services),
) -> dict[str, int]:
    value = json.dumps({"userId": user.user_id, "level": body.level, "message": body.message})
    try:
        _, offset = await svc.logs.publish(str(user.user_id), value.encode())
    except Unavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_KAFKA_DOWN) from None
    return {"id": offset}  # the Kafka offset: the id the stored row is shown with (partition 0)


@router.get("/logs")
async def list_logs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    user: TokenPayload = Depends(get_current_user),
) -> list[dict]:
    return await run_in_threadpool(repo.list_logs, _factory(request), user.user_id, limit)


@router.get("/logs/replay")
async def replay_logs(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    user: TokenPayload = Depends(get_current_user),
    svc: Services = Depends(services),
) -> dict:
    key = str(user.user_id)
    try:
        records = await svc.logs.replay(key, limit)
    except Unavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MSG_KAFKA_DOWN) from None
    messages = [m for r in records if r.key == key and (m := replay_message(r)) is not None]
    return {"fromBeginning": True, "messages": messages[:limit]}


# --- shared -------------------------------------------------------------------------------------------------


@router.delete("/events", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(check_origin)])
async def delete_events(request: Request, user: TokenPayload = Depends(write_limited)) -> Response:
    await run_in_threadpool(repo.delete_user_events, _factory(request), user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

