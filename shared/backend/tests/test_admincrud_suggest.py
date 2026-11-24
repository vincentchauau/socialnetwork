import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TableSpec, records_router
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(20))


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    token: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hid: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ro: Mapped[str | None] = mapped_column(String(30), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    spec = TableSpec(Post, owner="user_id", secret_columns=("token",), hidden_columns=("hid",), readonly_columns=("ro",))
    app.include_router(records_router([spec]), prefix="/records")
    cats = [(1, "Photography"), (1, "Photography"), (1, "Pets"), (2, "Photography"), (2, "photo_x"), (2, "Pho%to"), (2, "Zoo"), (2, None)]
    with engine.begin() as conn:
        conn.execute(User.__table__.insert(), [{"username": "Pam"}, {"username": "bob"}, {"username": "p_q"}])
        conn.execute(Post.__table__.insert(), [{"user_id": u, "category": c, "ro": "r", "token": "t", "hid": "h"} for u, c in cats])
    with TestClient(app) as c:
        yield c


def who(uid=1, group="user"):
    return {"Cookie": f"{COOKIE_NAME}={create_token(uid, 'u', group=group)}"}


ADMIN = who(9, "admin")
ME = who(1)


def get(client, path, headers, **params):
    return client.get(path, params=params, headers=headers)


def test_distinct_frequent_first_contains_and_case_insensitive(client):
    r = get(client, "/records/posts/suggest", ADMIN, column="category", q="P")
    assert r.status_code == 200
    assert r.json()["values"] == ["Photography", "Pets", "Pho%to", "photo_x"]
    values = get(client, "/records/posts/suggest", ADMIN, column="category", q="pho").json()["values"]
    assert values[0] == "Photography" and len(values) == len(set(values))
    assert "Zoo" not in get(client, "/records/posts/suggest", ADMIN, column="category", q="P").json()["values"]


def test_wildcards_escaped(client):
    assert get(client, "/records/posts/suggest", ADMIN, column="category", q="%").json()["values"] == ["Pho%to"]
    assert get(client, "/records/posts/suggest", ADMIN, column="category", q="o_x").json()["values"] == ["photo_x"]


def test_limit_and_empty_query(client):
    assert len(get(client, "/records/posts/suggest", ADMIN, column="category", q="o", limit=2).json()["values"]) == 2
    assert get(client, "/records/posts/suggest", ADMIN, column="category", q="o", limit=21).status_code == 422
    assert get(client, "/records/posts/suggest", ADMIN, column="category", q="").json() == {"values": []}


@pytest.mark.parametrize("col", ["token", "hid", "ro", "data", "blob", "nope", "id"])
def test_rejected_columns(client, col):
    assert get(client, "/records/posts/suggest", ADMIN, column=col, q="a").status_code == 422


def test_unknown_table_and_auth(client):
    assert get(client, "/records/nope/suggest", ADMIN, column="category", q="a").status_code == 404
    assert get(client, "/records/posts/suggest", ME, column="category", q="a").status_code == 200  # uniform gate
    assert get(client, "/records/posts/suggest", {}, column="category", q="a").status_code == 401
    assert get(client, "/records/posts/suggest", {}, column="category", q="a").status_code == 401


def test_data_only_own_values(client):
    values = get(client, "/records/posts/suggest", ME, column="category", q="o").json()["values"]
    assert values == ["Photography"]
    assert get(client, "/records/posts/suggest", ME, column="category", q="zoo").json()["values"] == []


def test_ref_options(client):
    r = get(client, "/records/posts/suggest", ADMIN, column="user_id", q="P").json()
    assert r["values"] == [] and r["options"] == [{"value": 1, "label": "Pam"}, {"value": 3, "label": "p_q"}]
    assert get(client, "/records/posts/suggest", ADMIN, column="user_id", q="_").json()["options"] == [{"value": 3, "label": "p_q"}]


def test_suggest_is_not_taken_as_pk(client):
    assert get(client, "/records/posts/suggest", ADMIN, column="category", q="z").json() == {"values": ["Zoo"]}
    assert client.get("/records/posts/1", headers=ADMIN).status_code == 200


def test_sort_asc_desc_with_pk_tiebreak(client):
    rows = get(client, "/records/posts", ADMIN, sort="category", limit=100).json()["rows"]
    cats = [r["category"] for r in rows]
    assert cats == sorted(cats, key=lambda c: (c is not None, c or ""))
    pets_first = [r["id"] for r in rows if r["category"] == "Photography"]
    assert pets_first == sorted(pets_first)
    desc = get(client, "/records/posts", ADMIN, sort="-id").json()["rows"]
    assert [r["id"] for r in desc] == sorted((r["id"] for r in desc), reverse=True)


@pytest.mark.parametrize("col", ["token", "hid", "data", "blob", "nope"])
def test_sort_and_filter_rejected_columns(client, col):
    assert get(client, "/records/posts", ADMIN, sort=col).status_code == 422
    assert get(client, "/records/posts", ADMIN, sort=f"-{col}").status_code == 422
    assert client.get(f"/records/posts?filter_{col}=x", headers=ADMIN).status_code == 422


def test_filters_exact_combined_and_total(client):
    r = client.get("/records/posts?filter_category=Photography", headers=ADMIN).json()
    assert r["total"] == 3 and len(r["rows"]) == 3
    r = client.get("/records/posts?filter_category=Photography&filter_user_id=2", headers=ADMIN).json()
    assert r["total"] == 1
    assert client.get("/records/posts?filter_user_id=1&q=pet", headers=ADMIN).json()["total"] == 1
    assert client.get("/records/posts?filter_user_id=abc", headers=ADMIN).status_code == 422
    assert client.get("/records/posts?other=1&filter_id=1", headers=ADMIN).json()["total"] == 1
    assert client.get("/records/posts?other=1", headers=ADMIN).json()["total"] == 8


def test_data_list_scoping_with_sort_and_filter(client):
    r = client.get("/records/posts?filter_category=Photography&sort=-id", headers=ME).json()
    assert r["total"] == 2 and all(row["user_id"] == 1 for row in r["rows"])
    assert client.get("/records/posts?filter_user_id=2", headers=ME).json()["total"] == 0
    assert client.get("/records/posts?filter_hid=h", headers=ME).status_code == 422
