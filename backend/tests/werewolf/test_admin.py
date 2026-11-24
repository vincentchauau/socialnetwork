from sqlalchemy import select

from api.werewolf.models import Game
from sn_shared import COOKIE_NAME, create_token

from tests.werewolf.conftest import auth_cookie

ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}


def test_admin_requires_admin_role(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers=auth_cookie()).status_code == 200


def test_admin_crud_on_games_masks_state(client):
    with client.app.state.session_factory() as db:
        db.add(Game(room_code="R1", status="live", state=b"secret-roles"))
        db.commit()
    tables = client.get("/records/tables", headers=ADMIN).json()
    assert [t["name"] for t in tables] == ["games"] and tables[0]["writable"] is True
    assert next(c for c in tables[0]["columns"] if c["name"] == "state")["secret"] is True
    row = client.get("/records/games", headers=ADMIN).json()["rows"][0]
    assert row["state"] == "***" and "secret-roles" not in str(row)
    assert client.patch(f"/records/games/{row['id']}", json={"values": {"state": "x"}}, headers=ADMIN).status_code == 422
    r = client.post("/records/games", json={"values": {"room_code": "R2", "status": "finished", "players": [{"user_id": 1}]}}, headers=ADMIN)
    assert r.status_code == 201 and r.json()["players"] == [{"user_id": 1}] and r.json()["state"] is None
    r = client.patch(f"/records/games/{r.json()['id']}", json={"values": {"winner": "WOLF"}}, headers=ADMIN)
    assert r.json()["winner"] == "WOLF"
    assert client.delete(f"/records/games/{r.json()['id']}", headers=ADMIN).status_code == 204
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(Game)).all()) == 1
