import pytest

from tests.market.conftest import BUYER, BUYER2, SELLER, auth, deliver, make_product, place_order


def review(client, product_id, who=BUYER, **body):
    payload = {"rating": 5, "content": "Great", **body}
    return client.post(f"/products/{product_id}/reviews", json=payload, headers=auth(who))


def delivered_product(client):
    lamp = make_product(client, stock=10)
    deliver(client, place_order(client, lamp["id"])["id"])
    return lamp


def test_review_requires_delivered_purchase(client):
    lamp = make_product(client)
    assert review(client, lamp["id"]).status_code == 403
    order = place_order(client, lamp["id"])
    assert review(client, lamp["id"]).status_code == 403  # pending is not enough
    deliver(client, order["id"])
    assert review(client, lamp["id"]).status_code == 201


def test_seller_and_strangers_cannot_review(client):
    lamp = delivered_product(client)
    assert review(client, lamp["id"], who=SELLER).status_code == 403
    assert review(client, lamp["id"], who=BUYER2).status_code == 403


def test_one_review_per_user(client):
    lamp = delivered_product(client)
    assert review(client, lamp["id"]).status_code == 201
    assert review(client, lamp["id"], rating=1).status_code == 409


@pytest.mark.parametrize(
    "body", [{"rating": 0}, {"rating": 6}, {"rating": 4.5}, {"rating": "5"}, {"content": "x" * 1001}]
)
def test_review_validation(client, body):
    lamp = delivered_product(client)
    assert review(client, lamp["id"], **body).status_code == 422


def test_review_unknown_product(client):
    assert review(client, 999).status_code == 404
    assert client.get("/products/999/reviews", headers=auth(BUYER)).status_code == 404


def test_reviews_list_and_rating_average(client):
    lamp = make_product(client, stock=10)
    for who, rating in ((BUYER, 5), (BUYER2, 2)):
        deliver(client, place_order(client, lamp["id"], who=who)["id"], buyer=who)
        assert review(client, lamp["id"], who=who, rating=rating, content=f"r{rating}").status_code == 201
    listed = client.get(f"/products/{lamp['id']}/reviews", headers=auth(BUYER)).json()
    assert [item["rating"] for item in listed] == [2, 5]
    assert "user_id" not in listed[0]
    page = client.get(
        f"/products/{lamp['id']}/reviews?limit=1&cursor={listed[0]['id']}", headers=auth(BUYER)
    ).json()
    assert [item["rating"] for item in page] == [5]
    product = client.get(f"/products/{lamp['id']}", headers=auth(BUYER)).json()
    assert product["rating_average"] == 3.5
    assert product["review_count"] == 2
    in_list = client.get("/products", headers=auth(BUYER)).json()["items"][0]
    assert in_list["rating_average"] == 3.5


def test_an_owner_edits_and_deletes_their_review_and_nobody_else_does(client):
    lamp = delivered_product(client)
    made = review(client, lamp["id"], rating=2, content="meh").json()
    assert client.patch(f"/reviews/{made['id']}", json={"rating": 5}, headers=auth(BUYER2)).status_code == 404
    assert client.delete(f"/reviews/{made['id']}", headers=auth(SELLER)).status_code == 404
    edited = client.patch(f"/reviews/{made['id']}", json={"rating": 5}, headers=auth(BUYER))
    assert edited.status_code == 200 and edited.json()["rating"] == 5 and edited.json()["content"] == "meh"
    assert client.patch(f"/reviews/{made['id']}", json={"rating": 9}, headers=auth(BUYER)).status_code == 422
    assert client.get(f"/products/{lamp['id']}", headers=auth(BUYER)).json()["rating_average"] == 5
    assert client.delete(f"/reviews/{made['id']}", headers=auth(BUYER)).status_code == 204
    assert client.get(f"/products/{lamp['id']}/reviews", headers=auth(BUYER)).json() == []
    assert review(client, lamp["id"]).status_code == 201  # and may review again
