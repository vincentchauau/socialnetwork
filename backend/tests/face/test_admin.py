from sn_shared import COOKIE_NAME, create_token

ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}


def test_admin_requires_admin_role(client, alice):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers=alice).status_code == 200


def test_admin_crud_measurement(client):
    assert [t["name"] for t in client.get("/records/tables", headers=ADMIN).json()] == ["measurements"]
    r = client.post("/records/measurements", json={"values": {"user_id": 1, "symmetry": 80}}, headers=ADMIN)
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert client.get("/records/measurements", headers=ADMIN).json()["total"] == 1
    r = client.patch(f"/records/measurements/{mid}", json={"values": {"symmetry": 90}}, headers=ADMIN)
    assert r.json()["symmetry"] == 90
    assert client.delete(f"/records/measurements/{mid}", headers=ADMIN).status_code == 204
    assert client.get(f"/records/measurements/{mid}", headers=ADMIN).status_code == 404
