from tests.market.conftest import BUYER, SELLER, auth, make_product


def test_a_person_saves_and_unsaves_a_product_and_sees_it_in_the_saved_list(client):
    product = make_product(client, SELLER, name="Lamp")
    pid = product["id"]
    assert client.put(f"/products/{pid}/save", headers=auth(BUYER)).status_code == 204
    assert client.put(f"/products/{pid}/save", headers=auth(BUYER)).status_code == 204  # saving twice is harmless
    saved = client.get("/me/saved-products", headers=auth(BUYER)).json()
    assert [item["id"] for item in saved] == [pid]
    assert client.delete(f"/products/{pid}/save", headers=auth(BUYER)).status_code == 204
    assert client.get("/me/saved-products", headers=auth(BUYER)).json() == []


def test_saved_products_are_private_and_a_missing_product_is_not_found(client):
    product = make_product(client, SELLER, name="Lamp")
    assert client.put(f"/products/{product['id']}/save", headers=auth(BUYER)).status_code == 204
    assert client.get("/me/saved-products", headers=auth(SELLER)).json() == []
    assert client.put("/products/999999/save", headers=auth(BUYER)).status_code == 404


def test_a_product_that_is_deleted_leaves_the_saved_list(client):
    product = make_product(client, SELLER, name="Lamp")
    client.put(f"/products/{product['id']}/save", headers=auth(BUYER))
    assert client.delete(f"/products/{product['id']}", headers=auth(SELLER)).status_code == 204
    assert client.get("/me/saved-products", headers=auth(BUYER)).json() == []
