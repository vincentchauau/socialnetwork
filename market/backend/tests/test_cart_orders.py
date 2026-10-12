import pytest

from app.payments import FakePaymentProvider
from tests.conftest import (
    BUYER,
    BUYER2,
    SELLER,
    SELLER2,
    add_to_cart,
    auth,
    checkout,
    deliver,
    make_product,
    place_order,
    set_status,
)


def stock_of(client, product_id: int) -> int:
    return client.get(f"/products/{product_id}", headers=auth(BUYER)).json()["stock"]


def test_cart_totals_use_db_prices(client):
    lamp = make_product(client, price_cents=2500)
    chair = make_product(client, name="Chair", price_cents=7000)
    add_to_cart(client, lamp["id"], 2)
    cart = add_to_cart(client, chair["id"], 1).json()
    assert cart["total_cents"] == 12000
    assert cart["item_count"] == 3
    assert cart["currency"] == "USD"
    client.put(
        f"/products/{lamp['id']}",
        json={"name": "Lamp", "price_cents": 100, "stock": 5},
        headers=auth(SELLER),
    )
    assert client.get("/cart", headers=auth(BUYER)).json()["total_cents"] == 7200


def test_cart_ignores_price_in_body(client):
    lamp = make_product(client)
    response = client.put(
        f"/cart/items/{lamp['id']}", json={"quantity": 1, "price_cents": 1}, headers=auth(BUYER)
    )
    assert response.status_code == 422


@pytest.mark.parametrize("quantity", [-1, 100, 1.5, "2", None])
def test_cart_quantity_validation(client, quantity):
    lamp = make_product(client)
    response = client.put(
        f"/cart/items/{lamp['id']}", json={"quantity": quantity}, headers=auth(BUYER)
    )
    assert response.status_code == 422


def test_cart_rules(client):
    lamp = make_product(client, stock=3)
    assert add_to_cart(client, lamp["id"], 1, who=SELLER).status_code == 403
    assert add_to_cart(client, 999).status_code == 404
    assert add_to_cart(client, lamp["id"], 4).status_code == 409
    assert add_to_cart(client, lamp["id"], 3).json()["items"][0]["quantity"] == 3
    assert add_to_cart(client, lamp["id"], 2).json()["items"][0]["quantity"] == 2


def test_cart_remove_by_zero_and_delete(client):
    lamp = make_product(client)
    add_to_cart(client, lamp["id"], 2)
    assert add_to_cart(client, lamp["id"], 0).json()["items"] == []
    add_to_cart(client, lamp["id"], 2)
    url = f"/cart/items/{lamp['id']}"
    assert client.delete(url, headers=auth(BUYER)).json()["items"] == []
    assert client.delete(url, headers=auth(BUYER)).status_code == 200


def test_carts_are_per_user(client):
    lamp = make_product(client)
    add_to_cart(client, lamp["id"], 1, who=BUYER)
    assert client.get("/cart", headers=auth(BUYER2)).json()["items"] == []


def test_deleted_product_leaves_carts(client):
    lamp = make_product(client)
    add_to_cart(client, lamp["id"], 1)
    client.delete(f"/products/{lamp['id']}", headers=auth(SELLER))
    assert client.get("/cart", headers=auth(BUYER)).json()["items"] == []
    assert add_to_cart(client, lamp["id"]).status_code == 404


def test_checkout_decrements_stock_and_snapshots(client):
    lamp = make_product(client, stock=5, price_cents=2500)
    order = place_order(client, lamp["id"], 2)
    assert order["status"] == "pending_payment"
    assert order["total_cents"] == 5000
    assert order["buyer_name"] == BUYER[1]
    assert order["items"][0] == {
        "product_id": lamp["id"],
        "name": "Lamp",
        "unit_price_cents": 2500,
        "quantity": 2,
        "line_total_cents": 5000,
    }
    assert stock_of(client, lamp["id"]) == 3
    assert client.get("/cart", headers=auth(BUYER)).json()["items"] == []
    # later edits do not change the snapshot
    client.put(
        f"/products/{lamp['id']}",
        json={"name": "Renamed", "price_cents": 9, "stock": 3},
        headers=auth(SELLER),
    )
    fetched = client.get(f"/orders/{order['id']}", headers=auth(BUYER)).json()
    assert fetched["items"][0]["name"] == "Lamp"
    assert fetched["total_cents"] == 5000


def test_checkout_empty_cart(client):
    assert checkout(client).status_code == 400


def test_no_overselling_second_buyer_loses(client):
    lamp = make_product(client, stock=1)
    add_to_cart(client, lamp["id"], 1, who=BUYER)
    add_to_cart(client, lamp["id"], 1, who=BUYER2)
    assert checkout(client, BUYER).status_code == 201
    loser = checkout(client, BUYER2)
    assert loser.status_code == 409
    assert stock_of(client, lamp["id"]) == 0
    # the failed checkout rolled back: the loser's cart is intact and no order exists
    assert len(client.get("/cart", headers=auth(BUYER2)).json()["items"]) == 1
    assert client.get("/orders", headers=auth(BUYER2)).json()["items"] == []


def test_checkout_is_all_or_nothing(client):
    lamp = make_product(client, stock=5)
    chair = make_product(client, name="Chair", stock=2)
    add_to_cart(client, lamp["id"], 1)
    add_to_cart(client, chair["id"], 2)
    # seller lowers chair stock below the cart quantity
    client.put(
        f"/products/{chair['id']}",
        json={"name": "Chair", "price_cents": 2500, "stock": 1},
        headers=auth(SELLER),
    )
    assert checkout(client).status_code == 409
    assert stock_of(client, lamp["id"]) == 5
    assert stock_of(client, chair["id"]) == 1
    assert len(client.get("/cart", headers=auth(BUYER)).json()["items"]) == 2


def test_checkout_idempotency_key_replays(client):
    lamp = make_product(client, stock=5)
    add_to_cart(client, lamp["id"], 1)
    first = checkout(client, **{"Idempotency-Key": "abc-1"})
    again = checkout(client, **{"Idempotency-Key": "abc-1"})
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert stock_of(client, lamp["id"]) == 4
    assert len(client.get("/orders", headers=auth(BUYER)).json()["items"]) == 1


def test_idempotency_key_is_per_user_and_validated(client):
    lamp = make_product(client, stock=5)
    add_to_cart(client, lamp["id"], 1, who=BUYER)
    add_to_cart(client, lamp["id"], 1, who=BUYER2)
    a = checkout(client, BUYER, **{"Idempotency-Key": "same"})
    b = checkout(client, BUYER2, **{"Idempotency-Key": "same"})
    assert a.json()["id"] != b.json()["id"]
    assert checkout(client, BUYER, **{"Idempotency-Key": "bad key!"}).status_code == 422
    assert checkout(client, BUYER, **{"Idempotency-Key": "k" * 129}).status_code == 422


def test_pay_flow_and_double_pay(client):
    lamp = make_product(client)
    order = place_order(client, lamp["id"])
    url = f"/orders/{order['id']}/pay"
    assert client.post(url, headers=auth(BUYER2)).status_code == 404
    assert client.post(url, headers=auth(SELLER)).status_code == 404
    paid = client.post(url, headers=auth(BUYER))
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    assert "payment_reference" not in paid.json()
    assert client.post(url, headers=auth(BUYER)).status_code == 409
    assert client.post("/orders/999/pay", headers=auth(BUYER)).status_code == 404


def test_pay_idempotency_key_replays(client):
    lamp = make_product(client)
    order = place_order(client, lamp["id"])
    url = f"/orders/{order['id']}/pay"
    headers = {**auth(BUYER), "Idempotency-Key": "pay-1"}
    assert client.post(url, headers=headers).status_code == 200
    replay = client.post(url, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["status"] == "paid"


def test_payment_failure_leaves_order_pending(declining_client):
    client = declining_client
    lamp = make_product(client)
    order = place_order(client, lamp["id"])
    response = client.post(f"/orders/{order['id']}/pay", headers=auth(BUYER))
    assert response.status_code == 402
    still = client.get(f"/orders/{order['id']}", headers=auth(BUYER)).json()
    assert still["status"] == "pending_payment"


def test_fake_provider_reference():
    result = FakePaymentProvider().charge(1, 100, "USD")
    assert result.reference.startswith("fake_")


def test_cancel_restocks(client):
    lamp = make_product(client, stock=5)
    order = place_order(client, lamp["id"], 3)
    assert stock_of(client, lamp["id"]) == 2
    assert set_status(client, order["id"], "cancelled", BUYER2).status_code == 404
    cancelled = set_status(client, order["id"], "cancelled", BUYER)
    assert cancelled.json()["status"] == "cancelled"
    assert stock_of(client, lamp["id"]) == 5
    assert set_status(client, order["id"], "cancelled", BUYER).status_code == 409
    assert stock_of(client, lamp["id"]) == 5


def test_cancel_after_pay_but_not_after_shipping(client):
    lamp = make_product(client, stock=5)
    order = place_order(client, lamp["id"])
    client.post(f"/orders/{order['id']}/pay", headers=auth(BUYER))
    assert set_status(client, order["id"], "shipped", SELLER).status_code == 200
    assert set_status(client, order["id"], "cancelled", BUYER).status_code == 409
    assert stock_of(client, lamp["id"]) == 4


def test_status_machine_and_roles(client):
    lamp = make_product(client)
    order = place_order(client, lamp["id"])
    oid = order["id"]
    assert set_status(client, oid, "shipped", SELLER).status_code == 409  # not paid yet
    client.post(f"/orders/{oid}/pay", headers=auth(BUYER))
    assert set_status(client, oid, "shipped", BUYER).status_code == 403  # buyer cannot ship
    assert set_status(client, oid, "cancelled", SELLER).status_code == 403  # seller cannot cancel
    assert set_status(client, oid, "shipped", SELLER2).status_code == 404  # not involved
    assert set_status(client, oid, "delivered", SELLER).status_code == 403  # sellers never deliver
    assert set_status(client, oid, "delivered", BUYER).status_code == 409  # skip not allowed
    assert set_status(client, oid, "paid", SELLER).status_code == 403
    assert set_status(client, oid, "shipped", SELLER).json()["status"] == "shipped"
    assert set_status(client, oid, "delivered", SELLER).status_code == 403
    assert set_status(client, oid, "delivered", BUYER).json()["status"] == "delivered"
    assert set_status(client, oid, "shipped", SELLER).status_code == 409
    bad = client.patch(f"/orders/{oid}/status", json={"status": "bogus"}, headers=auth(SELLER))
    assert bad.status_code == 422


def test_order_visibility_and_listings(client):
    lamp = make_product(client, who=SELLER, name="Lamp", price_cents=1000)
    chair = make_product(client, who=SELLER2, name="Chair", price_cents=4000)
    add_to_cart(client, lamp["id"], 1)
    add_to_cart(client, chair["id"], 2)
    order = checkout(client).json()
    assert order["total_cents"] == 9000
    oid = order["id"]

    as_seller = client.get(f"/orders/{oid}", headers=auth(SELLER)).json()
    assert [item["name"] for item in as_seller["items"]] == ["Lamp"]
    assert as_seller["total_cents"] == 1000
    assert client.get(f"/orders/{oid}", headers=auth(BUYER2)).status_code == 404
    assert client.get("/orders/999", headers=auth(BUYER)).status_code == 404

    assert len(client.get("/orders", headers=auth(BUYER)).json()["items"]) == 1
    assert client.get("/orders", headers=auth(SELLER)).json()["items"] == []
    sales = client.get("/sales", headers=auth(SELLER2)).json()["items"]
    assert [sale["total_cents"] for sale in sales] == [8000]
    assert client.get("/sales", headers=auth(BUYER)).json()["items"] == []


def test_orders_pagination(client):
    lamp = make_product(client, stock=10)
    ids = [place_order(client, lamp["id"])["id"] for _ in range(3)]
    first = client.get("/orders?limit=2", headers=auth(BUYER)).json()
    assert [order["id"] for order in first["items"]] == [ids[2], ids[1]]
    rest = client.get(f"/orders?limit=2&cursor={first['next_cursor']}", headers=auth(BUYER)).json()
    assert [order["id"] for order in rest["items"]] == [ids[0]]
    assert rest["next_cursor"] is None


def test_deleted_product_keeps_order_history(client):
    lamp = make_product(client)
    order = place_order(client, lamp["id"])
    client.delete(f"/products/{lamp['id']}", headers=auth(SELLER))
    fetched = client.get(f"/orders/{order['id']}", headers=auth(BUYER)).json()
    assert fetched["items"][0]["name"] == "Lamp"
    assert set_status(client, order["id"], "cancelled", BUYER).status_code == 200


def test_cannot_checkout_own_product_if_cart_was_seeded(client):
    # Defence in depth: checkout re-checks ownership even though the cart refuses it.
    from app.models import CartItem

    lamp = make_product(client)
    with client.app.state.session_factory() as session:
        session.add(CartItem(user_id=SELLER[0], product_id=lamp["id"], quantity=1))
        session.commit()
    assert checkout(client, SELLER).status_code == 403


def test_deliver_helper_reaches_delivered(client):
    lamp = make_product(client)
    order = place_order(client, lamp["id"])
    deliver(client, order["id"])
    assert client.get(f"/orders/{order['id']}", headers=auth(BUYER)).json()["status"] == "delivered"
