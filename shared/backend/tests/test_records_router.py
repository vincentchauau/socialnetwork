"""One address for everyone (`/records`): the group and `scope` decide what a call does (an admin sees every row, anyone else their own)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(40))
    internal: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Log(Base):
    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[str] = mapped_column(String(40))


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    mount_crud(app, [TableSpec(Note, owner="owner_id", user_hidden_columns=("internal",)), TableSpec(Log)])
    with engine.begin() as conn:
        conn.execute(Note.__table__.insert(), [{"owner_id": 1, "title": "mine", "internal": "i"}, {"owner_id": 2, "title": "bobs", "internal": "j"}])
        conn.execute(Log.__table__.insert(), [{"line": "boot"}])
    with TestClient(app) as c:
        yield c


def who(user_id, group="user"):
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, 'u', group=group)}"}


ANN, ROOT = who(1), who(9, "admin")


def titles(client, headers, **params):
    return sorted(row["title"] for row in client.get("/records/notes", params=params, headers=headers).json()["rows"])


def test_anonymous_is_refused(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/notes").status_code == 401


def test_a_person_sees_only_their_rows_and_an_admin_sees_all_unless_asked_for_their_own(client):
    assert titles(client, ANN) == ["mine"]
    assert titles(client, ROOT) == ["bobs", "mine"]
    assert titles(client, ROOT, scope="mine") == []  # the admin owns none
    assert titles(client, ROOT, scope="all") == ["bobs", "mine"]


def test_only_an_admin_may_ask_for_every_row_and_a_bad_scope_is_refused(client):
    assert client.get("/records/notes", params={"scope": "all"}, headers=ANN).status_code == 403
    assert client.get("/records/notes", params={"scope": "everything"}, headers=ROOT).status_code == 422
    assert client.post("/records/notes", params={"scope": "all"}, json={"values": {"title": "x"}}, headers=ANN).status_code == 403


def test_the_description_follows_the_role(client):
    mine = {t["name"]: t for t in client.get("/records/tables", headers=ANN).json()}
    assert set(mine) == {"notes"} and mine["notes"]["writable"] is True  # logs has no owner
    assert "internal" not in [c["name"] for c in mine["notes"]["columns"]]
    everything = {t["name"]: t for t in client.get("/records/tables", headers=ROOT).json()}
    assert set(everything) == {"notes", "logs"} and "internal" in [c["name"] for c in everything["notes"]["columns"]]


def test_a_table_with_no_view_for_a_person_is_not_there_for_them(client):
    assert client.get("/records/logs", headers=ANN).status_code == 404
    assert client.get("/records/logs", headers=ROOT).status_code == 200


def test_writes_keep_the_rules_of_each_scope(client):
    created = client.post("/records/notes", json={"values": {"title": "new", "owner_id": 2}}, headers=ANN)
    assert created.status_code == 422  # a person cannot give a row to someone else
    created = client.post("/records/notes", json={"values": {"title": "new"}}, headers=ANN)
    assert created.status_code == 201 and created.json()["owner_id"] == 1
    bobs = next(row["id"] for row in client.get("/records/notes", headers=ROOT).json()["rows"] if row["title"] == "bobs")
    assert client.patch(f"/records/notes/{bobs}", json={"values": {"title": "x"}}, headers=ANN).status_code == 404  # not theirs
    assert client.patch(f"/records/notes/{bobs}", json={"values": {"title": "fixed"}}, headers=ROOT).status_code == 200
    assert client.delete(f"/records/notes/{bobs}", headers=ANN).status_code == 404  # not theirs
    assert client.delete("/records/logs/1", headers=ROOT).status_code == 204


def test_sheet_changes_are_saved_per_row_and_only_by_an_admin(client):
    body = {"rows": [{"pk": "1", "values": {"title": "renamed"}}, {"pk": "99", "values": {"title": "nope"}}]}
    assert client.post("/records/notes/batch-update", json=body, headers=who(1)).status_code == 403
    done = client.post("/records/notes/batch-update", json=body, headers=who(9, "admin"))
    assert done.status_code == 200, done.text
    assert [r["ok"] for r in done.json()["results"]] == [True, False]
    assert done.json()["updated"] == 1
    assert client.get("/records/notes/1", headers=who(9, "admin")).json()["title"] == "renamed"
