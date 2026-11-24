from sn_shared import COOKIE_NAME, create_token

from tests.chat.conftest import auth_cookie

ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}
TABLES = {"rooms", "room_members", "messages", "edges", "reports", "notifications", "meetings"}


def test_admin_requires_admin_role(raw_client):
    assert raw_client.get("/records/tables").status_code == 401
    assert raw_client.get("/records/tables", headers=auth_cookie(1, "alice")).status_code == 200
    assert raw_client.post("/records/rooms", json={"values": {}}, headers=auth_cookie(1, "alice")).status_code == 405  # a person creates rooms through the room API


def test_admin_lists_every_chat_table_as_crud(raw_client):
    tables = {t["name"]: t for t in raw_client.get("/records/tables", headers=ADMIN).json()}
    assert set(tables) == TABLES
    assert all(t["writable"] is True for t in tables.values())


def test_admin_crud_on_a_room_and_a_message(raw_client):
    r = raw_client.post("/records/rooms", json={"values": {"slug": "adm", "title": "Adm", "user_id": 1}}, headers=ADMIN)
    assert r.status_code == 201
    room_id = r.json()["id"]
    r = raw_client.patch(f"/records/rooms/{room_id}", json={"values": {"state": "closed"}}, headers=ADMIN)
    assert r.json()["state"] == "closed"
    r = raw_client.post("/records/messages", json={"values": {"room_id": room_id, "user_id": 1, "content": "hi"}}, headers=ADMIN)
    assert r.status_code == 201
    message_id = r.json()["id"]
    assert raw_client.get("/records/messages?q=hi", headers=ADMIN).json()["total"] == 1
    assert raw_client.delete(f"/records/messages/{message_id}", headers=ADMIN).status_code == 204
    assert raw_client.delete(f"/records/rooms/{room_id}", headers=ADMIN).status_code == 204
    assert raw_client.get(f"/records/rooms/{room_id}", headers=ADMIN).status_code == 404


def test_admin_composite_keys_and_social_tables(raw_client):
    r = raw_client.post("/records/room_members", json={"values": {"room_id": 1, "user_id": 4}}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["status"] == "joined"
    assert raw_client.patch("/records/room_members/1~4", json={"values": {"status": "banned"}}, headers=ADMIN).json()["status"] == "banned"
    assert raw_client.patch("/records/room_members/1~4", json={"values": {"user_id": 5}}, headers=ADMIN).status_code == 422
    assert raw_client.delete("/records/room_members/1~4", headers=ADMIN).status_code == 204
    edge = {"src_id": 1, "dst_id": 2, "kind": "block"}
    assert raw_client.post("/records/edges", json={"values": edge}, headers=ADMIN).status_code == 201
    assert raw_client.delete("/records/edges/1~2~block", headers=ADMIN).status_code == 204
    note = {"user_id": 1, "kind": "friend_request", "payload": {"a": 1}}
    r = raw_client.post("/records/notifications", json={"values": note}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["payload"] == {"a": 1}
    report = {"reporter_id": 1, "target_type": "user", "target_id": "2", "reason": "spam"}
    assert raw_client.post("/records/reports", json={"values": report}, headers=ADMIN).status_code == 201


def test_deleting_a_room_as_admin_takes_its_members_and_messages_with_it(raw_client):
    room_id = raw_client.post("/records/rooms", json={"values": {"slug": "adm2", "title": "Adm", "user_id": 1}}, headers=ADMIN).json()["id"]
    raw_client.post("/records/messages", json={"values": {"room_id": room_id, "user_id": 1, "content": "hi"}}, headers=ADMIN)
    raw_client.post("/records/room_members", json={"values": {"room_id": room_id, "user_id": 1, "status": "joined"}}, headers=ADMIN)
    assert raw_client.delete(f"/records/rooms/{room_id}", headers=ADMIN).status_code == 204
    assert raw_client.get("/records/messages?q=hi", headers=ADMIN).json()["total"] == 0
    assert raw_client.get("/records/room_members", headers=ADMIN).json()["total"] == 0
