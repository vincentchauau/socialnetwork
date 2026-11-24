from api.roulette import game
from tests.roulette.conftest import ALICE, BOB


def bet(kind="red", amount=10, pick=None):
    return {"kind": kind, "pick": pick, "amount": amount}


def test_a_new_player_starts_with_chips(client):
    assert client.get("/wallet", headers=ALICE).json()["chips"] == 1000


def test_needs_sign_in(client):
    assert client.get("/wallet").status_code == 401
    assert client.post("/spin", json={"bets": [bet()]}).status_code == 401


def test_a_spin_settles_the_bets_against_the_wallet(client, monkeypatch):
    monkeypatch.setattr(game, "spin", lambda: 17)  # black, odd, 13..24
    response = client.post("/spin", json={"bets": [bet("black", 10), bet("red", 20), bet("straight", 5, 17)]}, headers=ALICE)
    assert response.status_code == 201
    body = response.json()
    assert body["number"] == 17 and body["colour"] == "black"
    assert body["stake"] == 35 and body["payout"] == 20 + 180
    assert body["balance_after"] == 1000 - 35 + 200 == client.get("/wallet", headers=ALICE).json()["chips"]


def test_a_losing_spin_takes_the_stake(client, monkeypatch):
    monkeypatch.setattr(game, "spin", lambda: 0)
    body = client.post("/spin", json={"bets": [bet("red", 100)]}, headers=ALICE).json()
    assert body["payout"] == 0 and body["balance_after"] == 900


def test_cannot_bet_more_than_the_chips(client, monkeypatch):
    monkeypatch.setattr(game, "spin", lambda: 0)
    for _ in range(2):
        assert client.post("/spin", json={"bets": [bet(amount=500)]}, headers=ALICE).status_code == 201
    assert client.post("/spin", json={"bets": [bet(amount=1)]}, headers=ALICE).status_code == 409


def test_bad_bets_are_refused(client):
    for bets in (
        [], [bet(amount=0)], [bet(amount=501)], [bet("straight")], [bet("straight", pick=37)], [bet("split", pick=304)], [bet("street", pick=2)], [bet("corner", pick=3)], [bet("line", pick=2)],
        [bet("red", pick=3)], [bet("dozen", pick=0)], [bet("nope")], [bet()] * 21,
    ):
        assert client.post("/spin", json={"bets": bets}, headers=ALICE).status_code == 422, bets


def test_refill_only_when_broke(client, monkeypatch):
    assert client.post("/wallet/refill", headers=ALICE).status_code == 409
    monkeypatch.setattr(game, "spin", lambda: 0)
    for _ in range(2):
        client.post("/spin", json={"bets": [bet("red", 500)]}, headers=ALICE)
    assert client.get("/wallet", headers=ALICE).json()["chips"] == 0
    assert client.post("/wallet/refill", headers=ALICE).json()["chips"] == 1000


def test_history_is_private_and_can_be_deleted(client):
    first = client.post("/spin", json={"bets": [bet()]}, headers=ALICE).json()
    client.post("/spin", json={"bets": [bet()]}, headers=BOB)
    assert [s["id"] for s in client.get("/spins", headers=ALICE).json()] == [first["id"]]
    assert client.delete(f"/spins/{first['id']}", headers=BOB).status_code == 404
    assert client.delete(f"/spins/{first['id']}", headers=ALICE).status_code == 204
    assert client.get("/spins", headers=ALICE).json() == []


def test_clear_history_only_clears_mine(client):
    client.post("/spin", json={"bets": [bet()]}, headers=ALICE)
    client.post("/spin", json={"bets": [bet()]}, headers=BOB)
    assert client.delete("/spins", headers=ALICE).status_code == 204
    assert client.get("/spins", headers=ALICE).json() == []
    assert len(client.get("/spins", headers=BOB).json()) == 1


def test_board_ranks_by_chips(client, monkeypatch):
    monkeypatch.setattr(game, "spin", lambda: 1)  # red
    client.post("/spin", json={"bets": [bet("red", 100)]}, headers=ALICE)
    client.post("/spin", json={"bets": [bet("black", 100)]}, headers=BOB)
    rows = client.get("/board", headers=ALICE).json()
    assert [(r["username"], r["chips"]) for r in rows] == [("alice", 1100), ("bob", 900)]


def test_account_events(client):
    from sn_shared.testing import add_person
    from api.roulette.account_events import on_user_deleted, on_user_renamed

    client.post("/spin", json={"bets": [bet()]}, headers=ALICE)
    add_person(client.app.state.session_factory, 1, "alicia")  # center renames the person
    with client.app.state.session_factory() as db:
        on_user_renamed(db, 1, "alicia")
        db.commit()
    assert client.get("/board", headers=ALICE).json()[0]["username"] == "alicia"
    with client.app.state.session_factory() as db:
        on_user_deleted(db, 1)
        on_user_deleted(db, 1)  # idempotent
        db.commit()
    assert client.get("/board", headers=BOB).json() == []
    assert client.get("/spins", headers=ALICE).json() == []


def test_stats_count_the_numbers_of_my_last_spins(client, monkeypatch):
    assert client.get("/stats", headers=ALICE).json() == {"spins": 0, "hot": [], "cold": []}
    for number in (17, 17, 5, 0):
        monkeypatch.setattr(game, "spin", lambda number=number: number)
        client.post("/spin", json={"bets": [bet("red", 1)]}, headers=ALICE)
    client.post("/spin", json={"bets": [bet("red", 1)]}, headers=BOB)
    body = client.get("/stats", headers=ALICE).json()
    assert body["spins"] == 4
    assert [(h["number"], h["count"]) for h in body["hot"]] == [(17, 2), (0, 1), (5, 1)]
    assert body["hot"][0]["colour"] == "black"
    assert [c["count"] for c in body["cold"]] == [0] * 5 and body["cold"][0]["number"] == 1
    assert client.get("/stats?last=1", headers=ALICE).json()["spins"] == 1
    assert client.get("/stats?last=0", headers=ALICE).status_code == 422
