from api.werewolf.models import Game, ids_text
from tests.werewolf.conftest import auth_cookie

ALICE = auth_cookie(1, "alice")


def seed(client):
    with client.app.state.session_factory() as db:
        db.add_all([
            Game(room_code="A", status="finished", winner="WOLF", player_ids=ids_text([1, 2]), players=[{"user_id": 1}]),
            Game(room_code="B", status="finished", winner="DRAW", player_ids=ids_text([2, 3])),
            Game(room_code="C", status="finished", winner="WOLF", player_ids=ids_text([11, 2])),  # 11 is not 1
            Game(room_code="D", status="live", state=b"secret-roles", player_ids=ids_text([1, 2])),
        ])
        db.commit()
        return {g.room_code: g.id for g in db.query(Game)}


def test_anonymous_is_401(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/games").status_code == 401


def test_only_my_finished_games_without_state(client):
    ids = seed(client)
    tables = client.get("/records/tables", headers=ALICE).json()
    assert [(t["name"], t["writable"]) for t in tables] == [("games", False)]
    assert "state" not in [c["name"] for c in tables[0]["columns"]]
    body = client.get("/records/games", headers=ALICE).json()
    assert body["total"] == 1 and body["rows"][0]["room_code"] == "A"
    assert "state" not in body["rows"][0]
    assert client.get(f"/records/games/{ids['A']}", headers=ALICE).status_code == 200


def test_other_peoples_and_live_games_are_404(client):
    ids = seed(client)
    for code in ("B", "C", "D"):
        assert client.get(f"/records/games/{ids[code]}", headers=ALICE).status_code == 404


def test_writes_are_405(client):
    ids = seed(client)
    assert client.post("/records/games", json={"values": {}}, headers=ALICE).status_code == 405
    assert client.patch(f"/records/games/{ids['A']}", json={"values": {"winner": "X"}}, headers=ALICE).status_code == 405
    assert client.delete(f"/records/games/{ids['A']}", headers=ALICE).status_code == 405
