import pytest

from tests.conftest import BUYER, SELLER, SELLER2, auth, make_product, product_body


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/products"),
        ("get", "/products/1"),
        ("get", "/me/products"),
        ("post", "/products"),
        ("put", "/products/1"),
        ("delete", "/products/1"),
        ("get", "/cart"),
        ("put", "/cart/items/1"),
        ("delete", "/cart/items/1"),
        ("post", "/orders"),
        ("get", "/orders"),
        ("get", "/sales"),
        ("get", "/orders/1"),
        ("post", "/orders/1/pay"),
        ("patch", "/orders/1/status"),
        ("get", "/products/1/reviews"),
        ("post", "/products/1/reviews"),
    ],
)
def test_requires_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_create_product_takes_identity_from_token(client):
    created = make_product(client)
    assert created["seller_id"] == SELLER[0]
    assert created["seller_name"] == SELLER[1]
    assert created["currency"] == "USD"
    assert created["category"] == "home"
    assert created["rating_average"] is None
    assert created["review_count"] == 0


def test_client_cannot_spoof_seller(client):
    body = product_body(seller_id=99)
    response = client.post("/products", json=body, headers=auth(SELLER))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 121},
        {"description": "x" * 4001},
        {"price_cents": 0},
        {"price_cents": -5},
        {"price_cents": 10.5},
        {"price_cents": "100"},
        {"price_cents": 1_000_000_001},
        {"stock": -1},
        {"stock": 1.5},
        {"image_url": "javascript:alert(1)"},
        {"image_url": "ftp://example.com/a.png"},
        {"image_url": "http://example.com/a.png"},
        {"image_url": "https://"},
        {"image_url": "https://exa mple.com/a.png"},
        {"image_url": "https://example.com/" + "a" * 500},
        {"category": "c" * 41},
    ],
)
def test_product_validation(client, overrides):
    response = client.post("/products", json=product_body(**overrides), headers=auth(SELLER))
    assert response.status_code == 422


def test_empty_image_url_becomes_none_and_defaults_apply(client):
    created = make_product(client, image_url="", description="")
    assert created["image_url"] is None
    minimal = client.post(
        "/products",
        json={"name": "N", "price_cents": 1, "stock": 0},
        headers=auth(SELLER),
    )
    assert minimal.status_code == 201
    assert minimal.json()["category"] == "other"


def test_get_product_and_404(client):
    created = make_product(client)
    assert client.get(f"/products/{created['id']}", headers=auth(BUYER)).json()["name"] == "Lamp"
    assert client.get("/products/9999", headers=auth(BUYER)).status_code == 404
    assert client.get("/products/0", headers=auth(BUYER)).status_code == 422


def test_update_by_owner_and_forbidden_for_others(client):
    created = make_product(client)
    url = f"/products/{created['id']}"
    updated = client.put(url, json=product_body(name="Big lamp", price_cents=3000), headers=auth(SELLER))
    assert updated.status_code == 200
    assert updated.json()["name"] == "Big lamp"
    assert updated.json()["price_cents"] == 3000
    assert client.put(url, json=product_body(), headers=auth(SELLER2)).status_code == 403
    assert client.put("/products/999", json=product_body(), headers=auth(SELLER)).status_code == 404


def test_delete_ownership_and_soft_delete(client):
    created = make_product(client)
    url = f"/products/{created['id']}"
    assert client.delete(url, headers=auth(SELLER2)).status_code == 403
    assert client.delete(url, headers=auth(SELLER)).status_code == 204
    assert client.get(url, headers=auth(SELLER)).status_code == 404
    assert client.delete(url, headers=auth(SELLER)).status_code == 404
    assert client.get("/products", headers=auth(BUYER)).json()["items"] == []


def test_my_products_only_lists_own(client):
    make_product(client, who=SELLER, name="mine")
    make_product(client, who=SELLER2, name="theirs")
    items = client.get("/me/products", headers=auth(SELLER)).json()["items"]
    assert [item["name"] for item in items] == ["mine"]


def test_search_and_filters(client):
    make_product(client, name="Red lamp", description="", category="home", price_cents=1000)
    make_product(client, name="Blue chair", description="", category="furniture", price_cents=5000, who=SELLER2)
    make_product(client, name="100% cotton", description="", category="clothes", price_cents=300)
    headers = auth(BUYER)

    def names(**params):
        response = client.get("/products", params=params, headers=headers)
        assert response.status_code == 200
        return {item["name"] for item in response.json()["items"]}

    assert names(q="lamp") == {"Red lamp"}
    assert names(q="LAMP") == {"Red lamp"}
    assert names(q="%") == {"100% cotton"}
    assert names(q="_") == set()
    assert names(category="Furniture") == {"Blue chair"}
    assert names(min_price=1000, max_price=5000) == {"Red lamp", "Blue chair"}
    assert names(seller=SELLER2[1]) == {"Blue chair"}
    assert names(q="  ") == {"Red lamp", "Blue chair", "100% cotton"}
    assert client.get("/products?min_price=10&max_price=5", headers=headers).status_code == 422
    assert client.get("/products?limit=51", headers=headers).status_code == 422
    assert client.get("/products?limit=0", headers=headers).status_code == 422
    assert client.get("/products?cursor=0", headers=headers).status_code == 422


def test_cursor_pagination(client):
    for index in range(5):
        make_product(client, name=f"p{index}")
    headers = auth(BUYER)
    first = client.get("/products?limit=2", headers=headers).json()
    assert [item["name"] for item in first["items"]] == ["p4", "p3"]
    second = client.get(f"/products?limit=2&cursor={first['next_cursor']}", headers=headers).json()
    assert [item["name"] for item in second["items"]] == ["p2", "p1"]
    last = client.get(f"/products?limit=2&cursor={second['next_cursor']}", headers=headers).json()
    assert [item["name"] for item in last["items"]] == ["p0"]
    assert last["next_cursor"] is None
