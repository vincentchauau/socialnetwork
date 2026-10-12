import inspect
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import cart, orders, products, reviews
from app.constants import DEFAULT_ORDER_TTL_MINUTES
from app.db import Base, make_engine
from app.models import utcnow
from app.payments import FakePaymentProvider, PaymentProvider
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./market.db"


def _start_account_consumer(session_factory: sessionmaker) -> Any:
    """Start center's account-event consumer; None in tests, without Redis or without the library."""
    if os.environ.get("TESTING") or not os.environ.get("REDIS_URL"):
        return None
    try:
        from sn_shared.events import start_account_consumer
    except ImportError:
        return None
    return start_account_consumer("market", session_factory)


async def _stop_account_consumer(handle: Any) -> None:
    stop = getattr(handle, "stop", None) or getattr(handle, "close", None)
    if stop is None:
        return
    result = stop()
    if inspect.isawaitable(result):
        await result


def create_app(
    database_url: str | None = None,
    payment_provider: PaymentProvider | None = None,
    clock: Callable[[], datetime] | None = None,
    order_ttl_minutes: float | None = None,
) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        handle = _start_account_consumer(application.state.session_factory)
        try:
            yield
        finally:
            if handle is not None:
                await _stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork market", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.payment_provider = payment_provider or FakePaymentProvider()
    app.state.clock = clock or utcnow
    if order_ttl_minutes is None:
        order_ttl_minutes = float(os.environ.get("ORDER_TTL_MINUTES", DEFAULT_ORDER_TTL_MINUTES))
    app.state.order_ttl = timedelta(minutes=order_ttl_minutes)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (products.router, cart.router, orders.router, reviews.router):
        app.include_router(router)
    return app


app = create_app()
