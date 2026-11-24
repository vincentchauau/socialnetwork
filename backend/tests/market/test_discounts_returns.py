from api.market.models import DiscountCode, Order

from .conftest import BUYER, SELLER, SELLER2, auth, add_to_cart, deliver, place_order, set_status


def _product(client, who=SELLER, price=1000, stock=10):
    response = client.post("/products", json={"name": "Thing", "price_cents": price, "stock": stock}, headers=auth(who))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _code(client, seller_id=SELLER[0], **fields):
    with client.app.state.session_factory() as db:
        db.add(DiscountCode(seller_id=seller_id, code=fields.pop("code", "SAVE10"), percent=fields.pop("percent", 10), **fields))
        db.commit()


def _buy(client, product_id, code=None, quantity=2):
    assert add_to_cart(client, product_id, quantity, BUYER).status_code == 200
    return client.post("/orders", json={"code": code} if code else None, headers=auth(BUYER))


def test_code_takes_a_percent_off_the_lines_of_its_seller(client):
    mine, other = _product(client), _product(client, SELLER2, price=500)
    _code(client)
    add_to_cart(client, other, 1, BUYER)
    response = _buy(client, mine, "save10")  # not case sensitive
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["discount_cents"] == 200 and order["discount_code"] == "SAVE10"
    assert order["total_cents"] == 2000 + 500 - 200
    seen_by_other = client.get(f"/orders/{order['id']}", headers=auth(SELLER2)).json()
    assert seen_by_other["discount_cents"] == 0 and seen_by_other["total_cents"] == 500


def test_code_that_is_not_valid_is_refused_and_the_cart_stays(client):
    product = _product(client)
    assert _buy(client, product, "NOPE").status_code == 400
    _code(client, code="OLD", expires_at=__import__("datetime").datetime(2000, 1, 1, tzinfo=__import__("datetime").timezone.utc))
    assert _buy(client, product, "OLD").status_code == 400
    _code(client, seller_id=SELLER2[0], code="OTHER")
    assert _buy(client, product, "OTHER").status_code == 400  # it is for products that are not in the cart
    assert client.get("/cart", headers=auth(BUYER)).json()["item_count"] == 2


def test_last_use_is_taken_once_and_given_back_when_the_order_is_cancelled(client):
    product = _product(client)
    _code(client, max_uses=1)
    order = _buy(client, product, "SAVE10").json()
    add_to_cart(client, product, 1, BUYER)
    assert client.post("/orders", json={"code": "SAVE10"}, headers=auth(BUYER)).status_code == 400
    assert set_status(client, order["id"], "cancelled", BUYER).status_code == 200
    assert client.post("/orders", json={"code": "SAVE10"}, headers=auth(BUYER)).status_code == 201


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
