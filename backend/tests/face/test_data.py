def test_data_requires_login(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/measurements").status_code == 401
    assert client.post("/records/measurements", json={"values": {"symmetry": 1}}).status_code == 401


def test_tables_and_ops(client, alice):
    tables = {t["name"]: t["writable"] for t in client.get("/records/tables", headers=alice).json()}
    assert tables == {"measurements": True}


def test_measurements_isolated_with_forced_owner(client, alice, bob):
    r = client.post("/records/measurements", json={"values": {"symmetry": 80}}, headers=alice)
    assert r.status_code == 201 and r.json()["user_id"] == 1
    mid = r.json()["id"]
    other = client.post("/records/measurements", json={"values": {"symmetry": 70}}, headers=bob).json()["id"]
    assert client.post("/records/measurements", json={"values": {"symmetry": 1, "user_id": 2}}, headers=alice).status_code == 422
    assert [x["id"] for x in client.get("/records/measurements", headers=alice).json()["rows"]] == [mid]
    assert client.get(f"/records/measurements/{other}", headers=alice).status_code == 404
    r = client.patch(f"/records/measurements/{mid}", json={"values": {"symmetry": 90}}, headers=alice)
    assert r.json()["symmetry"] == 90
    assert client.patch(f"/records/measurements/{other}", json={"values": {"symmetry": 1}}, headers=alice).status_code == 404
    assert client.patch(f"/records/measurements/{mid}", json={"values": {"user_id": 2}}, headers=alice).status_code == 422
    assert client.delete(f"/records/measurements/{other}", headers=alice).status_code == 404
    assert client.delete(f"/records/measurements/{mid}", headers=alice).status_code == 204
