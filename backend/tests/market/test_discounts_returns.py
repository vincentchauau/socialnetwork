from api.market import order_service
from api.market.models import Order

from .conftest import BUYER, SELLER, SELLER2, auth, add_to_cart, deliver, place_order, set_status


def _product(client, who=SELLER, price=1000, stock=10):
    response = client.post("/products", json={"name": "Thing", "price_cents": price, "stock": stock}, headers=auth(who))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_the_operator_percent_takes_off_the_whole_order(client, monkeypatch):
    monkeypatch.setattr(order_service, "ORDER_DISCOUNT_PERCENT", 10)
    mine, other = _product(client), _product(client, SELLER2, price=500)
    add_to_cart(client, other, 1, BUYER)
    add_to_cart(client, mine, 2, BUYER)
    response = client.post("/orders", headers=auth(BUYER))
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["discount_cents"] == 250 and order["total_cents"] == 2250
    assert "discount_code" not in order


def test_no_percent_means_no_discount(client):
    product = _product(client)
    add_to_cart(client, product, 2, BUYER)
    order = client.post("/orders", headers=auth(BUYER)).json()
    assert order["discount_cents"] == 0 and order["total_cents"] == 2000


def test_return_is_asked_by_the_buyer_and_accepted_by_the_seller(client):
    product = _product(client, stock=5)
    order = place_order(client, product, 2)
    assert set_status(client, order["id"], "return_requested", BUYER).status_code == 409  # not delivered yet
    deliver(client, order["id"])
    assert set_status(client, order["id"], "return_requested", SELLER).status_code == 403
    assert set_status(client, order["id"], "return_requested", BUYER).json()["status"] == "return_requested"
    assert set_status(client, order["id"], "returned", BUYER).status_code == 403
    assert set_status(client, order["id"], "returned", SELLER).json()["status"] == "returned"
    assert client.get(f"/products/{product}", headers=auth(BUYER)).json()["stock"] == 5  # what was bought is back in the stock


def test_seller_can_refuse_a_return(client):
    order = place_order(client, _product(client))
    deliver(client, order["id"])
    set_status(client, order["id"], "return_requested", BUYER)
    assert set_status(client, order["id"], "delivered", SELLER).json()["status"] == "delivered"


def test_return_after_the_window_is_refused(client):
    from datetime import timedelta
    from api.market.models import utcnow

    order = place_order(client, _product(client))
    deliver(client, order["id"])
    with client.app.state.session_factory() as db:
        db.get(Order, order["id"]).delivered_at = utcnow() - timedelta(days=30)
        db.commit()
    assert set_status(client, order["id"], "return_requested", BUYER).status_code == 409
