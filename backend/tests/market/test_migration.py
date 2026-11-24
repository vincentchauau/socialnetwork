"""The startup migration: order_items and idempotency_records move into `orders`."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from api.market.models import Order
from tests.market.conftest import BUYER, SELLER, SELLER2, auth, make_app

OLD_SCHEMA = [
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, buyer_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL,"
    " total_cents BIGINT NOT NULL, payment_reference VARCHAR(64), created_at DATETIME NOT NULL)",
    "CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, seller_id INTEGER,"
    " name VARCHAR(120), unit_price_cents BIGINT, quantity INTEGER)",
    "CREATE TABLE idempotency_records (id INTEGER PRIMARY KEY, user_id INTEGER, scope VARCHAR(64),"
    " key VARCHAR(128), order_id INTEGER)",
    "INSERT INTO orders VALUES (1, 3, 'paid', 700, 'ref', '2024-01-01 00:00:00.000000')",
    "INSERT INTO order_items VALUES (1, 1, 10, 1, 'Lamp', 100, 2), (2, 1, 11, 2, 'Chair', 250, 2)",
    "INSERT INTO idempotency_records VALUES (1, 3, 'checkout', 'ck-1', 1), (2, 3, 'pay:1', 'pay-1', 1)",
]


def test_old_tables_are_copied_into_orders_once(tmp_path):
    url = f"sqlite:///{tmp_path / 'market.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in OLD_SCHEMA:
            connection.execute(text(statement))

    with TestClient(make_app(url)) as client:
        seller = client.get("/sales", headers=auth(SELLER)).json()["items"]
        assert [(o["id"], [i["name"] for i in o["items"]], o["total_cents"]) for o in seller] == [(1, ["Lamp"], 200)]
        other = client.get("/sales", headers=auth(SELLER2)).json()["items"]
        assert [o["total_cents"] for o in other] == [500]
        assert client.get("/orders/1", headers=auth(BUYER)).json()["total_cents"] == 700

    with Session(engine) as db:
        order = db.get(Order, 1)
        assert (order.seller_ids, order.idempotency_key, order.pay_key) == ("|1|2|", "ck-1", "pay-1")
        assert [item["product_id"] for item in order.items] == [10, 11]
        db.execute(text("UPDATE order_items SET quantity = 9"))  # a later start must not copy again
        db.commit()

    with TestClient(make_app(url)) as client:
        assert client.get("/orders/1", headers=auth(BUYER)).json()["total_cents"] == 700
