import logging
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TableSpec, records_router
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys


install_test_keys()


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    locked: Mapped[int] = mapped_column(Integer, default=0)
    hid: Mapped[str | None] = mapped_column(String(10), nullable=True)


class Link(Base):
    __tablename__ = "links"
    a: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    b: Mapped[str] = mapped_column(String(10), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(20), nullable=True)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(
        records_router(
            [
                TableSpec(Item, secret_columns=("token",), readonly_columns=("locked",), hidden_columns=("hid",)),
                TableSpec(Link, label="Links"),
            ]
        ),
        prefix="/records",
    )
    with TestClient(app) as c:
        yield c


def cookie(group="admin", user_id=1):
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, 'u', group=group)}"}


ADMIN = cookie()


def make(client, name, **extra):
    r = client.post("/records/items", json={"values": {"name": name, **extra}}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()


def seed_links(client):
    from sqlalchemy import insert

    with client.app.state.session_factory() as s:
        s.execute(insert(Link.__table__), [{"a": 1, "b": "x", "label": "one"}, {"a": 2, "b": "y", "label": None}])
        s.commit()


def test_auth(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers=cookie("user")).status_code == 200  # uniform gate: a person sees own rows only
    assert client.post("/records/items", json={"values": {"name": "a"}}, headers=cookie("user")).status_code != 401
    assert client.get("/records/tables", headers=ADMIN).status_code == 200


def test_cross_origin_write_blocked(client):
    r = client.post("/records/items", json={"values": {"name": "a"}}, headers={**ADMIN, "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_tables_metadata(client):
    tables = {t["name"]: t for t in client.get("/records/tables", headers=ADMIN).json()}
    items = tables["items"]
    assert items["pk"] == ["id"] and items["writable"] is True and items["label"] == "items"
    cols = {c["name"]: c for c in items["columns"]}
    assert "hid" not in cols
    assert {n: c["type"] for n, c in cols.items()} == {
        "id": "int", "name": "string", "note": "text", "qty": "int", "price": "float", "active": "bool",
        "seen_at": "datetime", "meta": "json", "token": "string", "blob": "bytes", "locked": "int",
    }
    assert cols["token"]["secret"] and cols["blob"]["secret"] and cols["locked"]["readonly"]
    assert cols["note"]["nullable"] and not cols["name"]["nullable"]
    assert tables["links"]["pk"] == ["a", "b"] and "writable" in tables["links"]
    assert tables["links"]["label"] == "Links"


def test_create_get_patch_delete_roundtrip(client):
    row = make(
        client, "apple", qty="3", price=1.5, active="false", seen_at="2026-01-02T03:04:05Z", meta={"a": [1, 2]}
    )
    assert row["qty"] == 3 and row["active"] is False and row["meta"] == {"a": [1, 2]}
    assert row["seen_at"].startswith("2026-01-02T03:04:05")
    pk = row["id"]
    assert client.get(f"/records/items/{pk}", headers=ADMIN).json()["name"] == "apple"
    r = client.patch(f"/records/items/{pk}", json={"values": {"qty": 9, "note": None}}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["qty"] == 9 and r.json()["note"] is None
    assert client.delete(f"/records/items/{pk}", headers=ADMIN).status_code == 204
    assert client.get(f"/records/items/{pk}", headers=ADMIN).status_code == 404
    assert client.delete(f"/records/items/{pk}", headers=ADMIN).status_code == 404
    assert client.patch(f"/records/items/{pk}", json={"values": {"qty": 1}}, headers=ADMIN).status_code == 404


def test_paging_order_and_limit(client):
    for i in range(5):
        make(client, f"n{i}")
    body = client.get("/records/items?offset=1&limit=2", headers=ADMIN).json()
    assert body["total"] == 5 and [r["name"] for r in body["rows"]] == ["n3", "n2"]
    assert client.get("/records/items?limit=101", headers=ADMIN).status_code == 422
    assert client.get("/records/items?offset=-1", headers=ADMIN).status_code == 422
    assert client.get("/records/nope", headers=ADMIN).status_code == 404


def test_search_case_insensitive_and_wildcards_escaped(client):
    make(client, "Banana", note="yellow")
    make(client, "100%_real")
    make(client, "plain")
    names = lambda q: [r["name"] for r in client.get("/records/items", params={"q": q}, headers=ADMIN).json()["rows"]]
    assert names("banan") == ["Banana"]
    assert names("YELLOW") == ["Banana"]
    assert names("%") == ["100%_real"]
    assert names("_") == ["100%_real"]
    assert names("x'; DROP TABLE items;--") == []
    assert client.get("/records/items", headers=ADMIN).json()["total"] == 3


def test_search_terms_split_on_commas_all_must_match_and_column_prefix_narrows(client):
    make(client, "Red cloth", note="scene one")
    make(client, "Red hat", note="scene two")
    make(client, "Blue cloth", note="other")
    names = lambda q: sorted(r["name"] for r in client.get("/records/items", params={"q": q}, headers=ADMIN).json()["rows"])
    assert names("cloth, scene") == ["Red cloth"]
    assert names("red,scene") == ["Red cloth", "Red hat"]
    assert names("note:scene, cloth") == ["Red cloth"]
    assert names("name:scene") == []
    assert names("Red cloth") == ["Red cloth"]
    make(client, "Bag 2")
    make(client, "Bag 29")
    assert names("2") == ["Bag 2"]
    assert names("bag, 29") == ["Bag 29"]
    assert len(names(" , ")) == 5


def test_secret_and_bytes_redacted_and_not_writable(client):
    from sqlalchemy import update

    row = make(client, "s")
    with client.app.state.session_factory() as s:
        s.execute(update(Item.__table__).values(token="topsecret", blob=b"\x00\x01"))
        s.commit()
    got = client.get(f"/records/items/{row['id']}", headers=ADMIN).json()
    assert got["token"] == "***" and got["blob"] == "***"
    listed = client.get("/records/items", headers=ADMIN)
    assert "topsecret" not in listed.text and listed.json()["rows"][0]["token"] == "***"
    assert client.get("/records/items?q=topsecret", headers=ADMIN).json()["total"] == 0
    for col, val in (("token", "x"), ("blob", "x")):
        r = client.patch(f"/records/items/{row['id']}", json={"values": {col: val}}, headers=ADMIN)
        assert r.status_code == 422 and col in r.text


def test_validation_errors(client):
    row = make(client, "v")
    pk = row["id"]
    for values in ({"nope": 1}, {"locked": 5}, {"hid": "x"}, {"id": 99}, {"qty": "abc"}, {"qty": True},
                   {"active": "maybe"}, {"seen_at": "yesterday"}, {"price": "x"}, {"name": None}, {"name": 5}):
        r = client.patch(f"/records/items/{pk}", json={"values": values}, headers=ADMIN)
        assert r.status_code == 422, values
    r = client.post("/records/items", json={"values": {"qty": 1}}, headers=ADMIN)
    assert r.status_code == 422 and "name" in r.text
    assert client.post("/records/items", json={"values": {"name": "z", "locked": 1}}, headers=ADMIN).status_code == 422
    assert client.post("/records/items", json={"values": "no"}, headers=ADMIN).status_code == 422


def test_unique_violation_409_without_sql(client):
    make(client, "dup")
    other = make(client, "other")
    r = client.post("/records/items", json={"values": {"name": "dup"}}, headers=ADMIN)
    assert r.status_code == 409
    r2 = client.patch(f"/records/items/{other['id']}", json={"values": {"name": "dup"}}, headers=ADMIN)
    assert r2.status_code == 409
    for text in (r.text, r2.text):
        assert "INSERT" not in text and "UPDATE" not in text and "UNIQUE" not in text and "items" not in text


def test_composite_pk_and_read_delete_mode(client):
    seed_links(client)
    body = client.get("/records/links", headers=ADMIN).json()
    assert body["total"] == 2 and [(r["a"], r["b"]) for r in body["rows"]] == [(2, "y"), (1, "x")]
    assert client.get("/records/links/1~x", headers=ADMIN).json()["label"] == "one"
    assert client.get("/records/links/1", headers=ADMIN).status_code == 404
    assert client.get("/records/links/z~x", headers=ADMIN).status_code == 404
    assert client.post("/records/links", json={"values": {"a": 3, "b": "q"}}, headers=ADMIN).status_code == 201
    assert client.patch("/records/links/1~x", json={"values": {"label": "n"}}, headers=ADMIN).status_code == 200
    assert client.delete("/records/links/1~x", headers=ADMIN).status_code == 204
    assert client.get("/records/links", headers=ADMIN).json()["total"] == 2


def test_audit_logs_without_secret_values(client, caplog):
    caplog.set_level(logging.INFO, logger="sn_shared.admincrud")
    row = make(client, "audited")
    client.patch(f"/records/items/{row['id']}", json={"values": {"qty": 2}}, headers=cookie(user_id=7))
    client.delete(f"/records/items/{row['id']}", headers=cookie(user_id=7))
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 3
    assert "user_id=1 table=items pk=%d" % row["id"] in lines[0]
    assert lines[1].startswith("admin update") and "user_id=7" in lines[1]
    assert "audited" not in " ".join(lines)


def _hook_client(on_delete):
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(records_router([TableSpec(Item, on_delete=on_delete)]), prefix="/records")
    return TestClient(app)


def test_on_delete_hook_replaces_raw_delete_and_runs_after_commit():
    from sqlalchemy import delete, select

    calls = []

    def hook(request, db, row, user):
        calls.append(("hook", row["name"], user.user_id))
        db.execute(delete(Item.__table__).where(Item.__table__.c.id == row["id"]))
        return lambda: calls.append("after")

    with _hook_client(hook) as c:
        made = c.post("/records/items", json={"values": {"name": "h"}}, headers=ADMIN).json()
        assert c.delete(f"/records/items/{made['id']}", headers=cookie(user_id=4)).status_code == 204
        assert calls == [("hook", "h", 4), "after"]
        with c.app.state.session_factory() as s:
            assert s.scalar(select(Item.id)) is None


def test_on_delete_hook_can_refuse_and_rolls_back():
    from fastapi import HTTPException
    from sqlalchemy import delete

    def hook(request, db, row, user):
        db.execute(delete(Item.__table__))  # staged, must be rolled back by the refusal
        raise HTTPException(409, "refused")

    with _hook_client(hook) as c:
        made = c.post("/records/items", json={"values": {"name": "keep"}}, headers=ADMIN).json()
        r = c.delete(f"/records/items/{made['id']}", headers=ADMIN)
        assert r.status_code == 409 and r.json()["detail"] == "refused"
        assert c.get(f"/records/items/{made['id']}", headers=ADMIN).status_code == 200
