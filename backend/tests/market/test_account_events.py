import sys
import types

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from api.market.account_events import DELETED_USER_ID, on_user_deleted, on_user_renamed
from api.market.db import Base, make_engine
from api.market.main import create_app
from sn_shared.comments import Comment, ensure_table

from api.market.models import CartItem, Order, Product, seller_ids_text

SELLER, BUYER, OTHER = 1, 3, 4


def make_product(seller_id: int, name: str) -> Product:
    return Product(seller_id=seller_id, name=name, price_cents=100, stock=5)


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    ensure_table(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        lamp = make_product(SELLER, "Lamp")
        chair = make_product(OTHER, "Chair")
        session.add_all([lamp, chair])
        session.flush()
        bob_items = [
            {"product_id": lamp.id, "seller_id": SELLER, "name": "Lamp", "unit_price_cents": 100, "quantity": 1}
        ]
        beth_items = [
            {"product_id": chair.id, "seller_id": OTHER, "name": "Chair", "unit_price_cents": 100, "quantity": 1}
        ]
        bob_order = Order(
            buyer_id=BUYER, status="paid", total_cents=100, items=bob_items,
            seller_ids=seller_ids_text(bob_items), idempotency_key="k1", pay_key="p1",
        )
        beth_order = Order(
            buyer_id=OTHER, status="paid", total_cents=100, items=beth_items,
            seller_ids=seller_ids_text(beth_items), idempotency_key="k2",
        )
        session.add_all([bob_order, beth_order])
        session.flush()
        session.add_all(
            [
                CartItem(user_id=BUYER, product_id=chair.id, quantity=1),
                CartItem(user_id=OTHER, product_id=lamp.id, quantity=2),
                Comment(object_type="product", object_id=lamp.id, user_id=BUYER, rating=5, once=True),
                Comment(object_type="product", object_id=chair.id, user_id=BUYER, rating=4, once=True),
                Comment(object_type="product", object_id=chair.id, user_id=SELLER, rating=3, once=True),
            ]
        )
        session.commit()
        yield session


def snapshot(db):
    return {
        "market_products": [(p.seller_id, p.is_active, p.stock) for p in db.scalars(select(Product).order_by(Product.id))],
        "market_orders": [o.buyer_id for o in db.scalars(select(Order).order_by(Order.id))],
        "items": [i["seller_id"] for o in db.scalars(select(Order).order_by(Order.id)) for i in o.items],
        "seller_ids": [o.seller_ids for o in db.scalars(select(Order).order_by(Order.id))],
        "carts": [c.user_id for c in db.scalars(select(CartItem).order_by(CartItem.id))],
        "idem": [(o.idempotency_key, o.pay_key) for o in db.scalars(select(Order).order_by(Order.id))],
        "reviews": [(r.user_id, r.rating) for r in db.scalars(select(Comment).order_by(Comment.id))],
    }


def test_deleting_buyer_removes_cart_and_idempotency_and_anonymizes_orders_and_reviews(db):
    on_user_deleted(db, BUYER)
    snap = snapshot(db)
    assert snap["carts"] == [OTHER]
    assert snap["idem"] == [(None, None), ("k2", None)]
    assert snap["market_orders"] == [DELETED_USER_ID, OTHER]
    assert snap["reviews"] == [(-BUYER, 5), (-BUYER, 4), (SELLER, 3)]
    assert snap["market_products"] == [(SELLER, True, 5), (OTHER, True, 5)]


def test_deleting_seller_deactivates_and_anonymizes_products_and_order_lines(db):
    on_user_deleted(db, SELLER)
    snap = snapshot(db)
    assert snap["market_products"] == [(DELETED_USER_ID, False, 0), (OTHER, True, 5)]
    assert snap["items"] == [DELETED_USER_ID, OTHER]
    assert snap["seller_ids"] == ["", f"|{OTHER}|"]
    assert snap["reviews"][2] == (-SELLER, 3)
    assert snap["market_orders"] == [BUYER, OTHER]
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


def test_rename_changes_nothing_stored(db):
    before = snapshot(db)
    on_user_renamed(db, BUYER, "robert")
    on_user_renamed(db, 99, "nobody")
    on_user_renamed(db, DELETED_USER_ID, "ghost")
    assert snapshot(db) == before


class _Handle:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _fake_events(monkeypatch, calls: list, handle: _Handle):
    module = types.ModuleType("sn_shared.events")

    def start_account_consumer(app_name, session_factory, **_):
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
