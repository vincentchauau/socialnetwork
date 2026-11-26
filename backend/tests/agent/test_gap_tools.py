"""The rest of what the pages of jobs, market and face did: saved jobs, orders, reviews, history."""

import json

from tests.agent.test_tools import CALLS, clean, fake_http, post_tool  # noqa: F401  (clean resets the calls of each test)


def card(client, tool, args=None, confirmed=False, **fields):
    return post_tool(client, tool=tool, args=args or {}, confirmed=confirmed, **fields).json()["card"]


def labels(item):
    return [(a["label"], a["run"]) for a in item["actions"]]


# ---- jobs ----


def test_a_job_has_a_detail_with_apply_and_save_and_search_rows_have_buttons(client):
    job = {"id": 7, "title": "Python dev", "company": "Acme", "location": "Hà Nội", "remote": True, "employment_type": "full_time", "salary_min": 1000, "salary_max": None, "currency": "USD", "tags": ["python"], "description": "Build things"}
    client.app.state.http = fake_http({"/jobs/7": (200, job), "/jobs": (200, {"items": [job]})})
    detail = card(client, "jobs.job", {"job_id": 7})
    assert detail["type"] == "detail" and "remote" in detail["lines"][0] and labels(detail) == [("Apply", "ask")]
    row = card(client, "jobs.search", {"q": "py"})["items"][0]
    assert labels(row) == [("Open", "open")]


def test_withdrawing_an_application_asks_first_and_a_hired_one_cannot_be_withdrawn(client):
    rows = [{"id": 3, "job_id": 7, "job_title": "A", "company": "x", "status": "submitted"}, {"id": 4, "job_id": 8, "job_title": "B", "company": "y", "status": "hired"}]
    client.app.state.http = fake_http({"/me/applications": (200, rows)})
    items = card(client, "jobs.applications")["items"]
    assert labels(items[0]) == [("Withdraw", "ask")] and items[1]["actions"] == []
    client.app.state.http = fake_http({"/applications/3": (204, None)})
    CALLS.clear()
    assert card(client, "jobs.withdraw", {"application_id": 3})["type"] == "confirm" and CALLS == []
    assert card(client, "jobs.withdraw", {"application_id": 3}, True)["type"] == "done" and CALLS[0][0] == "DELETE"


def test_a_posting_can_be_edited_closed_or_removed_by_its_owner(client):
    posting = {"id": 5, "title": "Dev", "company": "Acme", "employment_type": "contract", "location": "", "remote": False, "salary_min": None, "salary_max": None, "description": "", "tags": [], "status": "open"}
    client.app.state.http = fake_http({"/me/jobs": (200, [{**posting, "id": 5}]), "/jobs/5": (200, posting)})
    row = card(client, "jobs.myjobs")["items"][0]
    assert labels(row) == [("Applicants", "open"), ("Edit", "open"), ("Remove", "ask")]
    form = card(client, "jobs.editpost", {"job_id": 5})
    assert form["args"] == {"job_id": 5} and {f["name"]: f.get("value") for f in form["fields"]}["status"] == "open"
    CALLS.clear()
    assert card(client, "jobs.editpost", {"job_id": 5, "status": "closed", "title": "Dev 2"}, True)["type"] == "done"
    assert CALLS[0][0] == "PATCH" and json.loads(CALLS[0][3]) == {"status": "closed", "title": "Dev 2"}
    CALLS.clear()
    assert card(client, "jobs.removepost", {"job_id": 5})["type"] == "confirm" and CALLS == []


# ---- market ----


def test_orders_have_the_buttons_that_fit_their_state_for_the_buyer_and_the_seller(client):
    orders = [{"id": i, "status": s, "total_cents": 1000, "buyer_username": "bob"} for i, s in enumerate(["pending_payment", "paid", "shipped", "delivered"], 1)]
    client.app.state.http = fake_http({"/sales": (200, {"items": orders}), "/orders": (200, {"items": orders})})
    mine = card(client, "market.orders")["items"]
    assert [[a["label"] for a in item["actions"]] for item in mine] == [["Pay", "Cancel"], ["Cancel"], ["I received it"], []]
    sold = card(client, "market.sales")["items"]
    assert [[a["label"] for a in item["actions"]] for item in sold] == [[], ["Mark shipped"], [], []]


def test_paying_and_changing_the_state_of_an_order_ask_first(client):
    client.app.state.http = fake_http({"/pay": (200, {"status": "paid"}), "/status": (200, {"status": "shipped"})})
    assert card(client, "market.pay", {"order_id": 1})["type"] == "confirm" and CALLS == []
    assert card(client, "market.pay", {"order_id": 1}, True)["summary"] == "Order #1 is paid" and len(CALLS[0][2]["Idempotency-Key"]) == 32
    assert card(client, "market.orderstatus", {"order_id": 1, "status": "shipped"}, True)["summary"] == "Order #1 is now shipped"
    assert CALLS[-1][0] == "PATCH" and json.loads(CALLS[-1][3]) == {"status": "shipped"}
    assert post_tool(client, tool="market.orderstatus", args={"order_id": 1, "status": "paid"}).status_code == 422  # only these three moves


def test_an_item_leaves_the_cart_with_one_press_and_reviews_are_read_and_written(client):
    client.app.state.http = fake_http({"/cart/items/4": (200, {})})
    assert card(client, "market.uncart", {"product_id": 4}, True)["type"] == "done" and CALLS[0][0] == "DELETE"
    client.app.state.http = fake_http({"/reviews": (200, [{"rating": 4, "username": "eve", "content": "Good"}])})
    item = card(client, "market.reviews", {"product_id": 4})["items"][0]
    assert item["title"] == "★★★★☆ eve" and item["subtitle"] == "Good"
    form = card(client, "market.review", {"product_id": 4})
    assert form["type"] == "form" and form["args"] == {"product_id": 4} and form["fields"][0]["options"][0]["label"] == "★★★★★"
    client.app.state.http = fake_http({"/reviews": (201, {})})
    CALLS.clear()
    assert card(client, "market.review", {"product_id": 4, "rating": "5", "content": "Great"}, True)["type"] == "done"
    assert json.loads(CALLS[0][3]) == {"rating": 5, "content": "Great"}




# ---- face ----


def test_a_measurement_or_the_whole_history_can_be_deleted_after_asking(client):
    client.app.state.http = fake_http({"/measurements": (200, [{"id": 3, "symmetry": 90, "createdAt": "2026-01-02T03:04:05Z"}])})
    assert labels(card(client, "face.history")["items"][0]) == [("Delete", "ask")]
    client.app.state.http = fake_http({"/measurements": (204, None)})
    CALLS.clear()
    assert card(client, "face.delete", {"measurement_id": 3})["type"] == "confirm" and card(client, "face.clear")["type"] == "confirm" and CALLS == []
    assert card(client, "face.delete", {"measurement_id": 3}, True)["type"] == "done" and CALLS[-1][1].endswith("/measurements/3")
    assert card(client, "face.clear", {}, True)["type"] == "done" and CALLS[-1][1].endswith("/measurements") and CALLS[-1][0] == "DELETE"
