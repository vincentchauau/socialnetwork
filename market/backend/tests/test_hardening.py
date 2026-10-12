from app.payments import FakePaymentProvider
from tests.conftest import (
    BUYER,
    SELLER,
    SELLER2,
    add_to_cart,
    auth,
    checkout,
    make_product,
    place_order,
    set_status,
)


def stock_of(client, product_id: int) -> int:
    return client.get(f"/products/{product_id}", headers=auth(BUYER)).json()["stock"]


def order_status(client, order_id: int) -> str:
    return client.get(f"/orders/{order_id}", headers=auth(BUYER)).json()["status"]


# --- 1. pending order expiry and cap ---------------------------------------------------


def test_expired_pending_order_is_cancelled_and_restocked_on_product_read(clock_client, clock):
    lamp = make_product(clock_client, stock=5)
    order = place_order(clock_client, lamp["id"], 3)
    clock.advance(minutes=14)
    assert stock_of(clock_client, lamp["id"]) == 2  # not yet expired
    clock.advance(minutes=2)
    assert stock_of(clock_client, lamp["id"]) == 5
    assert order_status(clock_client, order["id"]) == "cancelled"


def test_expiry_runs_on_listing_and_checkout(clock_client, clock):
    lamp = make_product(clock_client, stock=1)
    first = place_order(clock_client, lamp["id"], 1)
    clock.advance(minutes=20)
    listed = clock_client.get("/orders", headers=auth(BUYER)).json()["items"]
    assert listed[0]["status"] == "cancelled"
    # stock is back, so a second checkout works
    second = place_order(clock_client, lamp["id"], 1)
    assert second["id"] != first["id"]
    clock.advance(minutes=20)
    assert add_to_cart(clock_client, lamp["id"], 1).status_code == 200
    assert checkout(clock_client).status_code == 201


def test_expired_order_cannot_be_paid_and_paid_orders_never_expire(clock_client, clock):
    lamp = make_product(clock_client, stock=5)
    stale = place_order(clock_client, lamp["id"])
    fresh = place_order(clock_client, lamp["id"])
    clock_client.post(f"/orders/{fresh['id']}/pay", headers=auth(BUYER))
    clock.advance(minutes=60)
    assert clock_client.post(f"/orders/{stale['id']}/pay", headers=auth(BUYER)).status_code == 409
    assert order_status(clock_client, fresh["id"]) == "paid"
    assert stock_of(clock_client, lamp["id"]) == 4


def test_sales_listing_expires_too(clock_client, clock):
    lamp = make_product(clock_client, stock=2)
    place_order(clock_client, lamp["id"], 2)
    clock.advance(minutes=30)
    sales = clock_client.get("/sales", headers=auth(SELLER)).json()["items"]
    assert sales[0]["status"] == "cancelled"
    assert stock_of(clock_client, lamp["id"]) == 2


def test_pending_order_cap_per_buyer(client):
    lamp = make_product(client, stock=50)
    for _ in range(5):
        place_order(client, lamp["id"])
    add_to_cart(client, lamp["id"], 1)
    assert checkout(client).status_code == 409
    other = place_order(client, lamp["id"], who=(4, "beth"))  # other buyers unaffected
    assert other["status"] == "pending_payment"
    # paying one frees a slot
    first_id = client.get("/orders", headers=auth(BUYER)).json()["items"][-1]["id"]
    client.post(f"/orders/{first_id}/pay", headers=auth(BUYER))
    assert checkout(client).status_code == 201


# --- 2. only the buyer confirms delivery -----------------------------------------------


def test_seller_cannot_deliver_but_buyer_can(client):
    lamp = make_product(client)
    oid = place_order(client, lamp["id"])["id"]
    client.post(f"/orders/{oid}/pay", headers=auth(BUYER))
    set_status(client, oid, "shipped", SELLER)
    assert set_status(client, oid, "delivered", SELLER).status_code == 403
    assert order_status(client, oid) == "shipped"
    assert set_status(client, oid, "delivered", BUYER).status_code == 200


def test_multi_seller_order_second_seller_cannot_deliver(client):
    lamp = make_product(client, who=SELLER)
    chair = make_product(client, who=SELLER2, name="Chair")
    add_to_cart(client, lamp["id"])
    add_to_cart(client, chair["id"])
    oid = checkout(client).json()["id"]
    client.post(f"/orders/{oid}/pay", headers=auth(BUYER))
    assert set_status(client, oid, "shipped", SELLER).status_code == 200
    assert set_status(client, oid, "delivered", SELLER2).status_code == 403
    assert set_status(client, oid, "delivered", SELLER).status_code == 403


# --- 3. refunds on cancelling a paid order ---------------------------------------------


class RecordingProvider(FakePaymentProvider):
    def __init__(self) -> None:
        self.refunded: list[str] = []

    def refund(self, reference: str) -> None:
        self.refunded.append(reference)


def test_fake_provider_refund_is_noop_success():
    assert FakePaymentProvider().refund("fake_abc") is None


def test_cancel_paid_order_refunds(client):
    provider = RecordingProvider()
    client.app.state.payment_provider = provider
    lamp = make_product(client, stock=5)
    oid = place_order(client, lamp["id"], 2)["id"]
    client.post(f"/orders/{oid}/pay", headers=auth(BUYER))
    assert set_status(client, oid, "cancelled", BUYER).status_code == 200
    assert len(provider.refunded) == 1 and provider.refunded[0].startswith("fake_")
    assert stock_of(client, lamp["id"]) == 5


def test_cancel_pending_order_does_not_refund(client):
    provider = RecordingProvider()
    client.app.state.payment_provider = provider
    lamp = make_product(client)
    oid = place_order(client, lamp["id"])["id"]
    assert set_status(client, oid, "cancelled", BUYER).status_code == 200
    assert provider.refunded == []


def test_refund_failure_rolls_back_cancel(refund_failing_client):
    client = refund_failing_client
    lamp = make_product(client, stock=5)
    oid = place_order(client, lamp["id"], 2)["id"]
    client.post(f"/orders/{oid}/pay", headers=auth(BUYER))
    assert stock_of(client, lamp["id"]) == 3
    response = set_status(client, oid, "cancelled", BUYER)
    assert response.status_code == 502
    assert order_status(client, oid) == "paid"
    assert stock_of(client, lamp["id"]) == 3


# --- 4. cart distinct-product cap -------------------------------------------------------


def test_cart_distinct_product_cap(client):
    ids = [make_product(client, name=f"P{i}", stock=3)["id"] for i in range(51)]
    for product_id in ids[:50]:
        assert add_to_cart(client, product_id).status_code == 200
    assert add_to_cart(client, ids[50]).status_code == 409
    assert add_to_cart(client, ids[0], 2).status_code == 200  # updating an existing line is fine
    client.delete(f"/cart/items/{ids[1]}", headers=auth(BUYER))
    assert add_to_cart(client, ids[50]).status_code == 200


# --- 5. https only ---------------------------------------------------------------------


def test_http_image_url_rejected_https_accepted(client):
    response = client.post(
        "/products",
        json={"name": "A", "price_cents": 100, "stock": 1, "image_url": "http://x.com/a.png"},
        headers=auth(SELLER),
    )
    assert response.status_code == 422
    assert make_product(client, image_url="https://x.com/a.png")["image_url"] == "https://x.com/a.png"
