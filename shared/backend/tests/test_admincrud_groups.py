"""`/{table}/groups`: the values of a text column with how many rows hold each, for a board."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TableSpec, records_router
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    token: Mapped[str | None] = mapped_column(String(20), nullable=True)
    items: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ro: Mapped[str | None] = mapped_column(String(20), nullable=True)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    spec = TableSpec(Order, owner="user_id", secret_columns=("token",), readonly_columns=("ro",))
    app.include_router(records_router([spec]), prefix="/records")
    app.include_router(records_router([spec]), prefix="/records")
    rows = [(1, "paid"), (1, "paid"), (1, "shipped"), (2, "paid"), (2, "cancelled"), (2, None), (2, "")]
    with engine.begin() as conn:
        conn.execute(Order.__table__.insert(), [{"user_id": u, "status": s, "token": "t", "ro": "r"} for u, s in rows])
    with TestClient(app) as c:
        yield c


def who(uid=1, group="user"):
    return {"Cookie": f"{COOKIE_NAME}={create_token(uid, f'u{uid}', group=group)}"}


def values(reply):
    assert reply.status_code == 200, reply.text
    return [(item["value"], item["count"]) for item in reply.json()["values"]]


def test_an_admin_gets_every_value_with_its_count_the_most_common_first_and_without_blanks(client):
    assert values(client.get("/records/orders/groups?column=status", headers=who(9, "admin"))) == [("paid", 3), ("cancelled", 1), ("shipped", 1)]


def test_a_person_gets_the_counts_of_their_own_rows_only(client):
    assert values(client.get("/records/orders/groups?column=status", headers=who(1))) == [("paid", 2), ("shipped", 1)]
    assert values(client.get("/records/orders/groups?column=status", headers=who(2))) == [("cancelled", 1), ("paid", 1)]


def test_records_follows_the_role(client):
    assert values(client.get("/records/orders/groups?column=status", headers=who(9, "admin"))) == [("paid", 3), ("cancelled", 1), ("shipped", 1)]
    assert values(client.get("/records/orders/groups?column=status", headers=who(1))) == [("paid", 2), ("shipped", 1)]
    assert client.get("/records/orders/groups?column=status&scope=all", headers=who(1)).status_code == 403


def test_a_read_only_column_can_be_grouped_by_but_a_secret_one_a_document_and_an_unknown_one_cannot(client):
    admin = who(9, "admin")
    assert values(client.get("/records/orders/groups?column=ro", headers=admin)) == [("r", 7)]
    for column in ("token", "items", "nope"):
        assert client.get(f"/records/orders/groups?column={column}", headers=admin).status_code == 422, column


def test_the_limit_is_bounded_and_the_route_needs_a_session(client):
    assert client.get("/records/orders/groups?column=status&limit=51", headers=who(9, "admin")).status_code == 422
    assert client.get("/records/orders/groups?column=status&limit=1", headers=who(9, "admin")).json()["values"] == [{"value": "paid", "count": 3}]
    assert client.get("/records/orders/groups?column=status").status_code in (401, 403)
