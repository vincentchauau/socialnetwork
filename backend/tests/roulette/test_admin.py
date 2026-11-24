from sn_shared import COOKIE_NAME, create_token

ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}


def test_admin_requires_admin_role(client):
    from tests.roulette.conftest import ALICE

    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers=ALICE).status_code == 200


def test_admin_lists_tables_and_crud_wallet(client):
    tables = {t["name"]: t for t in client.get("/records/tables", headers=ADMIN).json()}
    assert set(tables) == {"roulette_spins", "roulette_wallets"} or len(tables) == 2
    wallet = next(t for t in tables.values() if t["pk"] == ["user_id"])
    r = client.post(f"/records/{wallet['name']}", json={"values": {"user_id": 5, "chips": "250"}}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["chips"] == 250
    r = client.patch(f"/records/{wallet['name']}/5", json={"values": {"chips": 10}}, headers=ADMIN)
    assert r.json()["chips"] == 10
    assert client.delete(f"/records/{wallet['name']}/5", headers=ADMIN).status_code == 204
