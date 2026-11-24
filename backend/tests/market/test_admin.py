from sqlalchemy import func, select

from api.market.models import CartItem, Order
from sn_shared import COOKIE_NAME, comments, create_token
from tests.market.conftest import BUYER, add_to_cart, auth, make_product, place_order

ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}


def _count(client, model) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_admin_requires_admin_role(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers=auth(BUYER)).status_code == 200
    assert client.delete("/records/market_products/1", headers=auth(BUYER)).status_code == 404


def test_admin_lists_the_market_tables(client):
    tables = {t["name"]: t for t in client.get("/records/tables", headers=ADMIN).json()}
    assert set(tables) == {"market_products", "cart_items", "market_orders", "discount_codes", "brands", "showcases"}
    assert tables["market_orders"]["writable"] is True


def test_admin_crud_product(client):
    values = {"seller_id": 1, "name": "Mug", "price_cents": 500, "stock": 3}
    r = client.post("/records/market_products", json={"values": values}, headers=ADMIN)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.patch(f"/records/market_products/{pid}", json={"values": {"stock": 9}}, headers=ADMIN).json()["stock"] == 9
    assert client.delete(f"/records/market_products/{pid}", headers=ADMIN).status_code == 204
    assert client.delete(f"/records/market_products/{pid}", headers=ADMIN).status_code == 404


def test_deleting_a_product_clears_carts_and_reviews_but_keeps_orders(client):
    product = make_product(client)
    other = make_product(client)
    place_order(client, other["id"])
    add_to_cart(client, product["id"])  # after checkout, which empties the cart
    with client.app.state.session_factory() as db:
        db.add(comments.Comment(object_type="product", object_id=product["id"], user_id=3, content="ok", rating=4))
        db.commit()
    assert _count(client, CartItem) == 1
    assert client.delete(f"/records/market_products/{product['id']}", headers=ADMIN).status_code == 204
    assert _count(client, CartItem) == 0 and _count(client, comments.Comment) == 0
    assert _count(client, Order) == 1


def test_orders_can_be_fixed_and_deleted_but_not_made_or_repriced(client):
    product = make_product(client)
    order = place_order(client, product["id"])
    assert client.get(f"/records/market_orders/{order['id']}", headers=ADMIN).status_code == 200
    fixed = client.patch(f"/records/market_orders/{order['id']}", json={"values": {"status": "paid", "payment_reference": "MANUAL-1"}}, headers=ADMIN)
    assert fixed.status_code == 200 and fixed.json()["status"] == "paid" and fixed.json()["payment_reference"] == "MANUAL-1"
    assert client.patch(f"/records/market_orders/{order['id']}", json={"values": {"total_cents": 1}}, headers=ADMIN).status_code == 422  # the money is the checkout's
    assert client.post("/records/market_orders", json={"values": {}}, headers=ADMIN).status_code == 422  # the admin may create; the values are checked
    assert client.delete(f"/records/market_orders/{order['id']}", headers=ADMIN).status_code == 204


def test_admin_crud_cart_item(client):
    product = make_product(client)
    values = {"user_id": 3, "product_id": product["id"], "quantity": 2}
    r = client.post("/records/cart_items", json={"values": values}, headers=ADMIN)
    assert r.status_code == 201, r.text
    row = r.json()["id"]
    assert client.patch(f"/records/cart_items/{row}", json={"values": {"quantity": 5}}, headers=ADMIN).json()["quantity"] == 5
    assert client.delete(f"/records/cart_items/{row}", headers=ADMIN).status_code == 204
