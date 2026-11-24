from sqlalchemy import insert

from api.roulette.models import Spin, Wallet
from tests.roulette.conftest import ALICE, BOB


def seed(client):
    with client.app.state.session_factory() as db:
        db.execute(insert(Wallet).values(user_id=1, chips=500))
        db.execute(insert(Wallet).values(user_id=2, chips=700))
        for uid in (1, 2):
            db.execute(insert(Spin).values(user_id=uid, number=7, bets=[], stake=1, payout=0, balance_after=9))
        db.commit()


def test_data_requires_login(client):
    assert client.get("/records/tables").status_code == 401


def test_data_tables_and_isolation(client):
    seed(client)
    tables = {t["name"]: t["writable"] for t in client.get("/records/tables", headers=ALICE).json()}
    assert tables == {"roulette_spins": True}
    assert client.get("/records/roulette_wallets/1", headers=ALICE).status_code == 404  # wallets are for admins
    assert client.get("/records/roulette_wallets/2", headers=ALICE).status_code == 404
    rows = client.get("/records/roulette_spins", headers=ALICE).json()["rows"]
    assert [r["user_id"] for r in rows] == [1]


def test_data_ops(client):
    seed(client)
    assert client.patch("/records/roulette_wallets/1", json={"values": {"chips": 9}}, headers=ALICE).status_code == 404  # wallets are for admins
    assert client.post("/records/roulette_spins", json={"values": {}}, headers=ALICE).status_code == 422  # own spins; the values are checked
    other = client.get("/records/roulette_spins", headers=BOB).json()["rows"][0]["id"]
    assert client.delete(f"/records/roulette_spins/{other}", headers=ALICE).status_code == 404
    assert client.delete(f"/records/roulette_spins/{other}", headers=BOB).status_code == 204
