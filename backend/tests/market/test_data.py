from sqlalchemy import func, select

from api.market.models import CartItem
from sn_shared import comments
from tests.market.conftest import BUYER, BUYER2, SELLER, SELLER2, add_to_cart, auth, make_product, place_order


def _count(client, model) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_data_requires_login(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/market_products").status_code == 401


def test_tables_and_ops(client):
    tables = {t["name"]: t["writable"] for t in client.get("/records/tables", headers=auth(BUYER)).json()}
    assert tables == {"market_products": True, "cart_items": True, "market_orders": False}


def test_products_isolated_and_seller_forced(client):
    mine = make_product(client, SELLER)
    other = make_product(client, SELLER2)
    assert [r["id"] for r in client.get("/records/market_products", headers=auth(SELLER)).json()["rows"]] == [mine["id"]]
    values = {"name": "Mug", "price_cents": 500, "stock": 3}
    r = client.post("/records/market_products", json={"values": values}, headers=auth(SELLER))
    assert r.status_code == 201 and r.json()["seller_id"] == SELLER[0]
    r = client.post("/records/market_products", json={"values": {**values, "seller_id": SELLER2[0]}}, headers=auth(SELLER))
    assert r.status_code == 422
    r = client.patch(f"/records/market_products/{other['id']}", json={"values": {"stock": 1}}, headers=auth(SELLER))
    assert r.status_code == 404


def test_deleting_a_product_runs_the_cleanup(client):
    product = make_product(client, SELLER)
    kept = make_product(client, SELLER)
    add_to_cart(client, product["id"], 1, BUYER2)
    with client.app.state.session_factory() as db:
        db.add(comments.Comment(object_type="product", object_id=product["id"], user_id=3, content="ok"))
        db.commit()
    other = make_product(client, SELLER2)
    assert client.delete(f"/records/market_products/{other['id']}", headers=auth(SELLER)).status_code == 404
    assert client.delete(f"/records/market_products/{product['id']}", headers=auth(SELLER)).status_code == 204
    assert _count(client, CartItem) == 0 and _count(client, comments.Comment) == 0
    assert client.get(f"/records/market_products/{kept['id']}", headers=auth(SELLER)).status_code == 200


def test_cart_items_isolated_and_owner_forced(client):
    product = make_product(client, SELLER)
    add_to_cart(client, product["id"], 1, BUYER)
    assert client.get("/records/cart_items", headers=auth(BUYER2)).json()["total"] == 0
    rows = client.get("/records/cart_items", headers=auth(BUYER)).json()["rows"]
    assert len(rows) == 1
    body = {"values": {"product_id": product["id"], "quantity": 2}}
    r = client.post("/records/cart_items", json=body, headers=auth(BUYER2))
    assert r.status_code == 201 and r.json()["user_id"] == BUYER2[0]
    assert client.delete(f"/records/cart_items/{rows[0]['id']}", headers=auth(BUYER2)).status_code == 404
    assert client.delete(f"/records/cart_items/{rows[0]['id']}", headers=auth(BUYER)).status_code == 204


def test_orders_for_buyer_and_sellers_only_without_keys(client):
    one = make_product(client, SELLER)
    two = make_product(client, SELLER2)
    order = place_order(client, one["id"], 1, BUYER)
    place_order(client, two["id"], 1, BUYER2)
    oid = order["id"]
    assert [r["id"] for r in client.get("/records/market_orders", headers=auth(SELLER)).json()["rows"]] == [oid]
    assert [r["id"] for r in client.get("/records/market_orders", headers=auth(BUYER)).json()["rows"]] == [oid]
    assert client.get(f"/records/market_orders/{oid}", headers=auth(BUYER2)).status_code == 404
    assert client.get(f"/records/market_orders/{oid}", headers=auth(SELLER2)).status_code == 404
    row = client.get(f"/records/market_orders/{oid}", headers=auth(BUYER)).json()
    assert "idempotency_key" not in row and "pay_key" not in row
    assert client.delete(f"/records/market_orders/{oid}", headers=auth(BUYER)).status_code == 405
    assert client.patch(f"/records/market_orders/{oid}", json={"values": {}}, headers=auth(BUYER)).status_code == 405
    assert client.post("/records/market_orders", json={"values": {}}, headers=auth(BUYER)).status_code == 405
