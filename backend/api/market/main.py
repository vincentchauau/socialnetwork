from sn_shared.deps import access_dependencies
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from api.market import cart, orders, products, reviews
from api.market.constants import DEFAULT_ORDER_TTL_MINUTES
from api.market.db import Base, make_engine
from api.market.migrate import migrate_orders
from sn_shared.db import ensure_foreign_key, rename_table
from api.market.models import utcnow
from api.market.payments import FakePaymentProvider, PaymentProvider
from sn_shared import comments, directory
from api.market import admin as admin_routes
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys

DEFAULT_DATABASE_URL = "sqlite:///./market.db"


stop_account_consumer = stop_consumer


def create_app(
    database_url: str | None = None,
    payment_provider: PaymentProvider | None = None,
    clock: Callable[[], datetime] | None = None,
    order_ttl_minutes: float | None = None,
) -> FastAPI:
    require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    rename_table(engine, "products", "market_products")  # the names of the tables before the market prefix
    rename_table(engine, "orders", "market_orders")
    Base.metadata.create_all(engine)
    for table in ("cart_items",):
        ensure_foreign_key(engine, table, "product_id", "market_products")
    migrate_orders(engine)  # an orders table made before items / idempotency keys moved into it
    directory.ensure_table_for_sqlite(engine)  # names are read from center's `users`
    comments.ensure_table(engine)  # what people say about a thing is one table (`sn_shared.comments`)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        handle = start_consumer("market", application.state.session_factory)
        try:
            yield
        finally:
            if handle is not None:
                await stop_account_consumer(handle)

    app = FastAPI(title="socialnetwork market", lifespan=lifespan)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    if payment_provider is None and os.environ.get("APP_ENV") == "production":
        raise RuntimeError("No payment provider is configured: the stub must not run in production")
    app.state.payment_provider = payment_provider or FakePaymentProvider()
    app.state.clock = clock or utcnow
    if order_ttl_minutes is None:
        order_ttl_minutes = float(os.environ.get("ORDER_TTL_MINUTES", DEFAULT_ORDER_TTL_MINUTES))
    app.state.order_ttl = timedelta(minutes=order_ttl_minutes)

    @app.get("/health", dependencies=access_dependencies(public=True))
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (products.router, cart.router, orders.router, reviews.router):
        app.include_router(router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
    admin_routes.mount(app)
    return app

