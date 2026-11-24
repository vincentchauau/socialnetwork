"""The cart, the orders, the applications, and the things that ask first: adding to the cart, buying, enrolling."""


from tests.agent.test_tools import CALLS, clean, fake_http, post_tool  # noqa: F401  (clean resets the calls of each test)


def test_the_cart_orders_and_applications_are_shown_as_lists(client):
    client.app.state.http = fake_http({
        "/cart": (200, {"items": [{"product_id": 4, "name": "Lamp", "quantity": 2, "line_total_cents": 2400}], "total_cents": 2400, "item_count": 2}),
        "/orders": (200, {"items": [{"id": 5, "status": "paid", "total_cents": 2400}], "next_cursor": None}),
        "/me/applications": (200, [{"id": 3, "job_id": 7, "job_title": "Python dev", "company": "Acme", "status": "applied"}]),
    })
    cart = post_tool(client, tool="market.cart", args={}).json()["card"]
    assert cart["title"] == "Cart: 24.00 (2)" and cart["items"][0]["title"] == "Lamp x2" and cart["items"][0]["actions"][0]["tool"] == "market.uncart"
    assert post_tool(client, tool="market.orders", args={}).json()["card"]["items"][0]["title"] == "#5 paid"
    assert post_tool(client, tool="jobs.applications", args={}).json()["card"]["items"][0]["subtitle"] == "Acme · applied"
    assert post_tool(client, tool="market.cart", args={"x": 1}).status_code == 422


