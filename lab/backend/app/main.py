import inspect
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app import routes
from app.db import Base, make_engine
from app.interfaces import Services
from app.limits import UserRateLimiter
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./lab.db"
MSG_INVALID = "Dữ liệu không hợp lệ."


def default_services() -> Services:
    """The real clients; none of them connects until it is used, so the app starts without the brokers."""
    from app.adapters.amqp import AmqpNotificationQueue
    from app.adapters.cache import RedisCache
    from app.adapters.kafka import KafkaLogBus
    from app.adapters.users import GrpcUserDirectory

    return Services(
        cache=RedisCache(os.environ.get("REDIS_URL")),
        users=GrpcUserDirectory(os.environ.get("GRPC_USER_TARGET", "lab-user:50051")),
        queue=AmqpNotificationQueue(),
        logs=KafkaLogBus(),
    )


def _start_account_consumer(session_factory: sessionmaker) -> Any:
    """Start center's account-event consumer; None in tests, without Redis or without the library."""
    if os.environ.get("TESTING") or not os.environ.get("REDIS_URL"):
        return None
    try:
        from sn_shared.events import start_account_consumer
    except ImportError:
        return None
    return start_account_consumer("lab", session_factory)


async def _stop_account_consumer(handle: Any) -> None:
    stop = getattr(handle, "stop", None) or getattr(handle, "close", None)
    if stop is None:
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"detail": MSG_INVALID}, status_code=422)


def create_app(database_url: str | None = None, services: Services | None = None) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Real clients are built here, inside the running event loop (grpc.aio needs one).
        clients = application.state.services = services or default_services()
        handle = _start_account_consumer(application.state.session_factory)
        try:
            yield
        finally:
            if handle is not None:
                await _stop_account_consumer(handle)
            for client in (clients.cache, clients.users, clients.queue, clients.logs):
                await client.close()

    app = FastAPI(title="socialnetwork lab", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.limiter = UserRateLimiter()
    app.state.services = services
    app.add_exception_handler(RequestValidationError, _invalid_request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(routes.router)
    return app


app = create_app()
