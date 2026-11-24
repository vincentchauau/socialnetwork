"""Forms, detail cards and buttons: jobs (post, applicants), the market (product, edit, remove)."""

import json

import pytest

from tests.agent.test_tools import CALLS, clean, fake_http, post_tool  # noqa: F401  (clean resets the calls of each test)


def fields_of(card):
    return {f["name"]: f for f in card["fields"]}


def test_posting_a_job_shows_a_form_first_and_a_sent_form_posts_it_as_the_caller(client):
    client.app.state.http = fake_http({})
    card = post_tool(client, tool="jobs.post", args={}).json()["card"]
    assert card["type"] == "form" and card["tool"] == "jobs.post" and card["args"] == {} and CALLS == []
    assert {"title", "company", "employment_type", "salary_min", "tags", "remote", "description"} <= set(fields_of(card))
    assert fields_of(card)["title"]["required"] is True and fields_of(card)["employment_type"]["kind"] == "select"
    client.app.state.http = fake_http({"/jobs": (201, {"id": 12, "title": "Python dev"})})
    sent = {"title": "Python dev", "company": "Acme", "employment_type": "contract", "remote": True, "tags": ["python"]}
    done = post_tool(client, tool="jobs.post", args=sent, confirmed=True).json()["card"]
    assert done["type"] == "done" and "#12" in done["summary"]
    assert json.loads(CALLS[0][3]) == {**sent, "currency": "USD", "location": "", "description": ""} and CALLS[0][2]["Cookie"] == "sn_token=tok"


def test_a_form_that_does_not_fit_says_which_field_and_a_service_refusal_says_why(client):
    client.app.state.http = fake_http({"/jobs": (422, {"detail": [{"loc": ["body", "salary_max"], "msg": "must not be below the minimum"}]})})
    bad = post_tool(client, tool="jobs.post", args={"title": "x", "company": "y", "employment_type": "nonsense"}, confirmed=True).json()["card"]
    assert bad["type"] == "error" and bad["summary"].startswith("employment_type") and CALLS == []
    refused = post_tool(client, tool="jobs.post", args={"title": "x", "company": "y", "employment_type": "contract"}, confirmed=True).json()["card"]
    assert refused == {"type": "error", "summary": "salary_max: must not be below the minimum"}


def test_the_applicants_have_buttons_for_what_can_still_be_done_to_them(client):
    rows = [
        {"id": 1, "applicant_username": "bob", "status": "submitted", "cover_letter": "Hello"},
        {"id": 2, "applicant_username": "eve", "status": "shortlisted", "cover_letter": "CV"},
        {"id": 3, "applicant_username": "joe", "status": "hired"},
    ]
    client.app.state.http = fake_http({"/applications": (200, rows)})
    items = post_tool(client, tool="jobs.applicants", args={"job_id": 5}).json()["card"]["items"]
    labels = [[a["label"] for a in item["actions"]] for item in items]
    assert labels == [["Shortlist", "Reject"], ["Interview", "Hire", "Reject"], []]  # hiring is not offered from the first step: the server would refuse it
    hire = items[1]["actions"][1]
    assert hire == {"label": "Hire", "tool": "jobs.setstatus", "args": {"application_id": 2, "status": "hired"}, "run": "ask"}
    assert items[0]["actions"][0]["run"] == "do"  # shortlisting is small; hiring and rejecting ask first


def test_changing_the_state_of_an_application_asks_and_then_patches(client):
    client.app.state.http = fake_http({"/applications/1": (200, {})})
    args = {"application_id": 1, "status": "hired"}
    assert post_tool(client, tool="jobs.setstatus", args=args).json()["card"]["type"] == "confirm" and CALLS == []
    assert post_tool(client, tool="jobs.setstatus", args=args, confirmed=True).json()["card"]["type"] == "done"
    assert CALLS[0][0] == "PATCH" and json.loads(CALLS[0][3]) == {"status": "hired"}
    assert post_tool(client, tool="jobs.setstatus", args={"application_id": 1, "status": "fired"}).status_code == 422


def test_a_product_is_a_detail_card_with_a_button_to_add_it_to_the_cart_and_only_a_local_image(client):
    product = {"id": 4, "name": "Lamp", "price_cents": 1200, "currency": "USD", "seller_username": "bob", "stock": 3, "category": "home", "description": "Bright", "image_url": "/api/art/files/x.png"}
    client.app.state.http = fake_http({"/products/4": (200, product)})
    card = post_tool(client, tool="market.product", args={"product_id": 4}).json()["card"]
    assert card["type"] == "detail" and card["title"] == "Lamp" and card["image"] == "/api/art/files/x.png"
    assert card["actions"][0] == {"label": "Add to cart", "tool": "market.addcart", "args": {"product_id": 4, "quantity": 1}, "run": "do"}
    assert [a["tool"] for a in card["actions"]] == ["market.addcart", "market.reviews", "market.review"]
    client.app.state.http = fake_http({"/products/4": (200, {**product, "image_url": "https://evil.example/x.png"})})
    assert "image" not in post_tool(client, tool="market.product", args={"product_id": 4}).json()["card"]


def test_my_products_have_edit_and_remove_and_the_edit_form_starts_from_the_product(client):
    product = {"id": 4, "name": "Lamp", "price_cents": 1250, "stock": 3, "category": "home", "description": "Bright", "image_url": None}
    client.app.state.http = fake_http({"/me/products": (200, {"items": [product]}), "/products/4": (200, product)})
    item = post_tool(client, tool="market.mine", args={}).json()["card"]["items"][0]
    assert [(a["label"], a["run"]) for a in item["actions"]] == [("Edit", "open"), ("Remove", "ask")]
    form = post_tool(client, tool="market.edit", args={"product_id": 4}).json()["card"]
    assert form["type"] == "form" and form["args"] == {"product_id": 4}
    assert (fields_of(form)["price"]["value"], fields_of(form)["name"]["value"], fields_of(form)["stock"]["value"]) == (12.5, "Lamp", 3)


def test_a_sent_edit_changes_only_what_was_sent_and_keeps_the_rest(client):
    product = {"id": 4, "name": "Lamp", "price_cents": 1250, "stock": 3, "category": "home", "description": "Bright", "image_url": None}
    client.app.state.http = fake_http({"/products/4": (200, product)})
    done = post_tool(client, tool="market.edit", args={"product_id": 4, "price": 9.99, "stock": 5}, confirmed=True).json()["card"]
    assert done["type"] == "done"
    method, _, _, body = CALLS[-1]
    assert method == "PUT" and json.loads(body) == {"name": "Lamp", "description": "Bright", "price_cents": 999, "stock": 5, "category": "home", "image_url": None}


def test_removing_a_product_asks_first(client):
    client.app.state.http = fake_http({"/products/4": (204, None)})
    assert post_tool(client, tool="market.remove", args={"product_id": 4}).json()["card"]["type"] == "confirm" and CALLS == []
    assert post_tool(client, tool="market.remove", args={"product_id": 4}, confirmed=True).json()["card"]["type"] == "done"
    assert CALLS[0][0] == "DELETE"


def test_every_form_tool_opens_without_a_token_as_an_error_and_unknown_opening_arguments_are_refused(client):
    client.app.state.http = fake_http({})
    assert post_tool(client, tool="jobs.post", args={}, token="").json()["card"]["type"] == "error"
    assert post_tool(client, tool="market.edit", args={}).status_code == 422
    assert post_tool(client, tool="jobs.post", args={"evil": 1}).status_code == 422
    with pytest.raises(KeyError):
        from api.chat.agent import tools

        tools.run_tool("nothing.here", {}, "t", False)
