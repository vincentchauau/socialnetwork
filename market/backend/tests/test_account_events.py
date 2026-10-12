import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.account_events import DELETED_USER_ID, DELETED_USERNAME, on_user_deleted, on_user_renamed
from app.db import Base, make_engine
from app.main import create_app
from app.models import CartItem, IdempotencyRecord, Order, OrderItem, Product, Review

SELLER, BUYER, OTHER = 1, 3, 4


def make_product(seller_id: int, seller_name: str, name: str) -> Product:
    return Product(
        seller_id=seller_id, seller_name=seller_name, name=name, price_cents=100, stock=5
    )


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        lamp = make_product(SELLER, "sally", "Lamp")
        chair = make_product(OTHER, "beth", "Chair")
        session.add_all([lamp, chair])
        session.flush()
        bob_order = Order(buyer_id=BUYER, buyer_name="bob", status="paid", currency="USD", total_cents=100)
        bob_order.items.append(
            OrderItem(product_id=lamp.id, seller_id=SELLER, name="Lamp", unit_price_cents=100, quantity=1)
        )
        beth_order = Order(buyer_id=OTHER, buyer_name="beth", status="paid", currency="USD", total_cents=100)
        beth_order.items.append(
            OrderItem(product_id=chair.id, seller_id=OTHER, name="Chair", unit_price_cents=100, quantity=1)
        )
        session.add_all([bob_order, beth_order])
        session.flush()
        session.add_all(
            [
                CartItem(user_id=BUYER, product_id=chair.id, quantity=1),
                CartItem(user_id=OTHER, product_id=lamp.id, quantity=2),
                IdempotencyRecord(user_id=BUYER, scope="checkout", key="k1", order_id=bob_order.id),
                IdempotencyRecord(user_id=OTHER, scope="checkout", key="k2", order_id=beth_order.id),
                Review(product_id=lamp.id, user_id=BUYER, username="bob", rating=5),
                Review(product_id=chair.id, user_id=BUYER, username="bob", rating=4),
                Review(product_id=chair.id, user_id=SELLER, username="sally", rating=3),
            ]
        )
        session.commit()
        yield session


def snapshot(db):
    return {
        "products": [(p.seller_id, p.seller_name, p.is_active, p.stock) for p in db.scalars(select(Product).order_by(Product.id))],
        "orders": [(o.buyer_id, o.buyer_name) for o in db.scalars(select(Order).order_by(Order.id))],
        "items": [i.seller_id for i in db.scalars(select(OrderItem).order_by(OrderItem.id))],
        "carts": [c.user_id for c in db.scalars(select(CartItem).order_by(CartItem.id))],
        "idem": [r.user_id for r in db.scalars(select(IdempotencyRecord).order_by(IdempotencyRecord.id))],
        "reviews": [(r.user_id, r.username, r.rating) for r in db.scalars(select(Review).order_by(Review.id))],
    }


def test_deleting_buyer_removes_cart_and_idempotency_and_anonymizes_orders_and_reviews(db):
    on_user_deleted(db, BUYER)
    snap = snapshot(db)
    assert snap["carts"] == [OTHER]
    assert snap["idem"] == [OTHER]
    assert snap["orders"] == [(DELETED_USER_ID, DELETED_USERNAME), (OTHER, "beth")]
    assert snap["reviews"] == [
        (-BUYER, DELETED_USERNAME, 5),
        (-BUYER, DELETED_USERNAME, 4),
        (SELLER, "sally", 3),
    ]
    assert snap["products"] == [(SELLER, "sally", True, 5), (OTHER, "beth", True, 5)]


def test_deleting_seller_deactivates_and_anonymizes_products_and_order_lines(db):
    on_user_deleted(db, SELLER)
    snap = snapshot(db)
    assert snap["products"] == [(DELETED_USER_ID, DELETED_USERNAME, False, 0), (OTHER, "beth", True, 5)]
    assert snap["items"] == [DELETED_USER_ID, OTHER]
    assert snap["reviews"][2] == (-SELLER, DELETED_USERNAME, 3)
    assert snap["orders"] == [(BUYER, "bob"), (OTHER, "beth")]
    assert snap["carts"] == [BUYER, OTHER]


def test_delete_is_idempotent(db):
    on_user_deleted(db, BUYER)
    on_user_deleted(db, SELLER)
    first = snapshot(db)
    on_user_deleted(db, BUYER)
    on_user_deleted(db, SELLER)
    assert snapshot(db) == first


def test_delete_user_without_data_changes_nothing(db):
    before = snapshot(db)
    on_user_deleted(db, 99)
    on_user_deleted(db, DELETED_USER_ID)
    assert snapshot(db) == before


def test_rename_updates_every_denormalized_column(db):
    on_user_renamed(db, BUYER, "robert")
    on_user_renamed(db, SELLER, "sarah")
    snap = snapshot(db)
    assert [p[1] for p in snap["products"]] == ["sarah", "beth"]
    assert snap["orders"] == [(BUYER, "robert"), (OTHER, "beth")]
    assert snap["reviews"] == [(BUYER, "robert", 5), (BUYER, "robert", 4), (SELLER, "sarah", 3)]


def test_rename_is_idempotent_and_safe_without_data(db):
    on_user_renamed(db, BUYER, "robert")
    first = snapshot(db)
    on_user_renamed(db, BUYER, "robert")
    on_user_renamed(db, 99, "nobody")
    on_user_renamed(db, DELETED_USER_ID, "ghost")
    assert snapshot(db) == first


class _Handle:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _fake_events(monkeypatch, calls: list, handle: _Handle):
    module = types.ModuleType("sn_shared.events")

    def start_account_consumer(app_name, session_factory):
        calls.append((app_name, session_factory))
        return handle

    module.start_account_consumer = start_account_consumer
    monkeypatch.setitem(sys.modules, "sn_shared.events", module)


def test_consumer_starts_and_stops_with_lifespan(monkeypatch):
    calls, handle = [], _Handle()
    _fake_events(monkeypatch, calls, handle)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(create_app("sqlite://")):
        assert [name for name, _ in calls] == ["market"]
        assert not handle.stopped
    assert handle.stopped


def test_consumer_not_started_without_redis_or_when_testing(monkeypatch):
    calls = []
    _fake_events(monkeypatch, calls, _Handle())
    monkeypatch.delenv("REDIS_URL", raising=False)
    with TestClient(create_app("sqlite://")):
        pass
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("TESTING", "1")
    with TestClient(create_app("sqlite://")):
        pass
    assert calls == []


def test_missing_events_library_is_tolerated(monkeypatch):
    monkeypatch.setitem(sys.modules, "sn_shared.events", None)  # import raises ImportError
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(create_app("sqlite://")) as client:
        assert client.get("/health").status_code == 200


def test_handle_without_stop_method_is_tolerated(monkeypatch):
    _fake_events(monkeypatch, [], object())
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("TESTING", raising=False)
    with TestClient(create_app("sqlite://")):
        pass
