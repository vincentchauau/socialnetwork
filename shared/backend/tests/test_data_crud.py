import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TableSpec, records_router
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
    pinned: Mapped[int] = mapped_column(Integer, default=0)
    secret: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    internal: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))


class Member(Base):
    __tablename__ = "members"
    room_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    nick: Mapped[str | None] = mapped_column(String(20), nullable=True)


class Locked(Base):
    __tablename__ = "locked"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


def room_scope(db, user):
    return Room.id.in_(Member.__table__.select().with_only_columns(Member.room_id).where(Member.user_id == user.user_id))


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    specs = [
        TableSpec(
            Note,
            owner="owner_id",
            secret_columns=("secret",),
            user_readonly_columns=("pinned",),
            user_hidden_columns=("internal",)),
        TableSpec(Room, scope=room_scope),
        TableSpec(Member, owner="user_id"),
        TableSpec(Locked, owner="user_id"),
    ]
    app.include_router(records_router(specs), prefix="/records")
    with engine.begin() as conn:
        conn.execute(Room.__table__.insert(), [{"name": "mine"}, {"name": "other"}])
        conn.execute(
            Member.__table__.insert(),
            [{"room_id": 1, "user_id": 1, "nick": "a"}, {"room_id": 2, "user_id": 2, "nick": "b"}],
        )
        conn.execute(
            Note.__table__.insert(),
            [
                {"owner_id": 2, "title": "bobs", "secret": "s", "blob": b"x", "internal": "i"},
            ],
        )
    with TestClient(app) as c:
        yield c


def who(user_id=1, group="user"):
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, 'u', group=group)}"}


ME = who(1)
BOB = who(2)


def test_anonymous_is_401(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/notes").status_code == 401
    assert client.post("/records/notes", json={"values": {"title": "x"}}).status_code == 401


def test_tables_lists_only_user_tables_with_writable(client):
    tables = {t["name"]: t for t in client.get("/records/tables", headers=ME).json()}
    assert set(tables) == {"notes", "rooms", "members", "locked"}  # a table with an owner or a scope is open to its people
    assert tables["notes"]["writable"] is True and tables["rooms"]["writable"] is False
    assert "internal" not in [c["name"] for c in tables["notes"]["columns"]]


def test_ownership_isolation(client):
    assert client.get("/records/notes", headers=ME).json() == {"total": 0, "rows": []}
    assert client.get("/records/notes/1", headers=ME).status_code == 404
    assert client.patch("/records/notes/1", json={"values": {"title": "x"}}, headers=ME).status_code == 404
    assert client.delete("/records/notes/1", headers=ME).status_code == 404
    assert client.get("/records/notes/1", headers=BOB).status_code == 200
    assert client.get("/records/notes?q=bobs", headers=ME).json()["total"] == 0


def test_admin_token_is_scoped_too(client):
    assert client.get("/records/notes/1?scope=mine", headers=who(1, "admin")).status_code == 404  # an admin asking for their own rows is scoped too


def test_create_forces_owner(client):
    r = client.post("/records/notes", json={"values": {"title": "mine"}}, headers=ME)
    assert r.status_code == 201 and r.json()["owner_id"] == 1
    r = client.post("/records/notes", json={"values": {"title": "m", "owner_id": 1}}, headers=ME)
    assert r.status_code == 201
    r = client.post("/records/notes", json={"values": {"title": "m", "owner_id": 2}}, headers=ME)
    assert r.status_code == 422
    assert client.get("/records/notes", headers=ME).json()["total"] == 2


def test_update_and_delete_own_row(client):
    nid = client.post("/records/notes", json={"values": {"title": "a"}}, headers=ME).json()["id"]
    r = client.patch(f"/records/notes/{nid}", json={"values": {"title": "b"}}, headers=ME)
    assert r.status_code == 200 and r.json()["title"] == "b"
    for bad in ("owner_id", "id", "pinned", "internal", "secret", "blob"):
        r = client.patch(f"/records/notes/{nid}", json={"values": {bad: 5}}, headers=ME)
        assert r.status_code == 422, bad
    assert client.delete(f"/records/notes/{nid}", headers=ME).status_code == 204
    assert client.get(f"/records/notes/{nid}", headers=ME).status_code == 404


def test_people_cannot_write_a_table_without_an_owner(client):
    assert client.post("/records/rooms", json={"values": {"name": "x"}}, headers=ME).status_code == 405
    assert client.delete("/records/rooms/1", headers=ME).status_code == 405


def test_custom_scope(client):
    rows = client.get("/records/rooms", headers=ME).json()["rows"]
    assert [r["name"] for r in rows] == ["mine"]
    assert client.get("/records/rooms/1", headers=ME).status_code == 200
    assert client.get("/records/rooms/2", headers=ME).status_code == 404


def test_hidden_and_redaction(client):
    row = client.get("/records/notes/1", headers=BOB).json()
    assert "internal" not in row
    assert row["secret"] == "***" and row["blob"] == "***"


def test_composite_pk(client):
    assert client.get("/records/members/1~1", headers=ME).json()["nick"] == "a"
    assert client.get("/records/members/2~2", headers=ME).status_code == 404
    assert client.delete("/records/members/2~2", headers=ME).status_code == 404
    assert client.delete("/records/members/1~1", headers=ME).status_code == 204


def test_on_delete_hook_gets_the_person():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    seen = []

    def hook(request, db, row, user):
        seen.append((row["id"], user.user_id))
        db.execute(Note.__table__.delete().where(Note.id == row["id"]))

    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(
        records_router([TableSpec(Note, owner="owner_id", on_delete=hook)]), prefix="/records"
    )
    with TestClient(app) as c:
        nid = c.post("/records/notes", json={"values": {"title": "t"}}, headers=ME).json()["id"]
        assert c.delete(f"/records/notes/{nid}", headers=ME).status_code == 204
    assert seen == [(nid, 1)]


def test_spec_validation():
    with pytest.raises(ValueError):
        TableSpec(Note, groups=("ghost",))
    with pytest.raises(ValueError):
        TableSpec(Note, owner="nope")
