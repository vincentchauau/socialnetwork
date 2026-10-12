import os

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import cart, orders, products, reviews
from app.db import Base, make_engine
from app.payments import FakePaymentProvider, PaymentProvider
from sn_shared.security import get_jwt_secret

DEFAULT_DATABASE_URL = "sqlite:///./market.db"


def create_app(
    database_url: str | None = None, payment_provider: PaymentProvider | None = None
) -> FastAPI:
    get_jwt_secret()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    app = FastAPI(title="socialnetwork market")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.payment_provider = payment_provider or FakePaymentProvider()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (products.router, cart.router, orders.router, reviews.router):
        app.include_router(router)
    return app


app = create_app()
