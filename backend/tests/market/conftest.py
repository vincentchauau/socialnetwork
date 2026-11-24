import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
from sn_shared.testing import add_person, install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from api.market.main import create_app  # noqa: E402
from api.market.payments import PaymentError, PaymentResult  # noqa: E402
from sn_shared import COOKIE_NAME, create_token  # noqa: E402

SELLER = (1, "sally")
SELLER2 = (2, "sam")
BUYER = (3, "bob")
BUYER2 = (4, "beth")


def make_app(database_url: str = "sqlite://", **kwargs: Any):
    """create_app plus a `users` row for every test person (names are read from center's table)."""
    app = create_app(database_url, **kwargs)
    for user_id, username in (SELLER, SELLER2, BUYER, BUYER2):
        add_person(app.state.session_factory, user_id, username)
    return app


class DecliningProvider:
    def charge(self, order_id: int, amount_cents: int, currency: str) -> PaymentResult:
        raise PaymentError("declined")

    def refund(self, reference: str) -> None:
        raise PaymentError("declined")


class RefundFailingProvider:
    def charge(self, order_id: int, amount_cents: int, currency: str) -> PaymentResult:
        return PaymentResult(reference="fake_ok")

    def refund(self, reference: str) -> None:
        raise PaymentError("refund failed")


class ManualClock:
    """Real time plus an adjustable offset, so created_at defaults stay comparable."""

    def __init__(self) -> None:
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(timezone.utc) + self.offset

    def advance(self, **kwargs: float) -> None:
        self.offset += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    with TestClient(make_app()) as test_client:
        yield test_client


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def clock_client(clock):
    with TestClient(make_app(clock=clock, order_ttl_minutes=15)) as test_client:
        yield test_client


@pytest.fixture
def refund_failing_client():
    with TestClient(make_app(payment_provider=RefundFailingProvider())) as test_client:
        yield test_client


@pytest.fixture
def declining_client():
    with TestClient(make_app(payment_provider=DecliningProvider())) as test_client:
        yield test_client


def auth(who: tuple[int, str]) -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(*who)}"}


def product_body(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "Lamp",
        "description": "A nice lamp",
        "price_cents": 2500,
        "stock": 5,
        "image_url": "https://example.com/lamp.png",
        "category": "Home",
        **overrides,
    }


def make_product(client: TestClient, who=SELLER, **overrides: Any) -> dict[str, Any]:
    response = client.post("/products", json=product_body(**overrides), headers=auth(who))
    assert response.status_code == 201, response.text
    return response.json()


def add_to_cart(client: TestClient, product_id: int, quantity: int = 1, who=BUYER):
    return client.put(f"/cart/items/{product_id}", json={"quantity": quantity}, headers=auth(who))


def checkout(client: TestClient, who=BUYER, **headers: str):
    return client.post("/orders", headers={**auth(who), **headers})


def place_order(client: TestClient, product_id: int, quantity: int = 1, who=BUYER) -> dict[str, Any]:
    assert add_to_cart(client, product_id, quantity, who).status_code == 200
    response = checkout(client, who)
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client: TestClient, order_id: int, status: str, who):
    return client.patch(f"/orders/{order_id}/status", json={"status": status}, headers=auth(who))


def deliver(client: TestClient, order_id: int, seller=SELLER, buyer=BUYER) -> None:
    assert client.post(f"/orders/{order_id}/pay", headers=auth(buyer)).status_code == 200
    assert set_status(client, order_id, "shipped", seller).status_code == 200
    assert set_status(client, order_id, "delivered", buyer).status_code == 200
