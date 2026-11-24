import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TOMBSTONE_LABEL, TableSpec, records_router
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(20))


class Skill(Base):
    __tablename__ = "skills"
    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(20))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(20))


class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skill_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ghost_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hidden_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    secret_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


REFS = {
    "job_id": ("jobs", "title"),
    "skill_key": ("skills", "name", "key"),
    "ghost_id": ("nowhere", "name"),
    "hidden_id": ("jobs", "title"),
    "secret_id": ("jobs", "title"),
}


def spec():
    return TableSpec(Item, owner="user_id", hidden_columns=("hidden_id",), secret_columns=("secret_id",), refs=REFS)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(records_router([spec()]), prefix="/records")
    with engine.begin() as conn:
        conn.execute(User.__table__.insert(), [{"id": 1, "username": "ann"}, {"id": 2, "username": "bob"}])
        conn.execute(Job.__table__.insert(), [{"id": 1, "title": "Dev"}, {"id": 2, "title": "Ops"}])
        conn.execute(Skill.__table__.insert(), [{"key": "py", "name": "Python"}])
        base = {"skill_key": None, "ghost_id": 5, "hidden_id": 1, "secret_id": 1}
        conn.execute(
            Item.__table__.insert(),
            [
                {**base, "user_id": 1, "job_id": 1, "skill_key": "py"},
                {**base, "user_id": 1, "job_id": 99},
                {**base, "user_id": 1, "job_id": 2},
                {**base, "user_id": 0, "job_id": None},
            ],
        )
    with TestClient(app) as c:
        yield c


ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}
ME = {"Cookie": f"{COOKIE_NAME}={create_token(1, 'ann')}"}


def test_unknown_ref_column_is_rejected():
    with pytest.raises(ValueError):
        TableSpec(Item, refs={"nope": ("jobs", "title")})
    with pytest.raises(ValueError):
        TableSpec(Item, refs={"job_id": ("jobs",)})


def test_tables_describe_refs_and_default_user_ref(client):
    cols = {c["name"]: c for c in client.get("/records/tables", headers=ADMIN).json()[0]["columns"]}
    assert cols["user_id"]["ref"] == {"table": "users", "label": "username", "key": "id"}
    assert cols["job_id"]["ref"] == {"table": "jobs", "label": "title", "key": "id"}
    assert "ref" not in cols["id"]
    assert "hidden_id" not in cols and "ref" not in cols["secret_id"] and "ref" not in cols["blob"]


@pytest.mark.parametrize("prefix,headers,first", [
    ("/records", ADMIN, {"user_id": {"0": TOMBSTONE_LABEL}}),
    ("/records", ME, {"user_id": {"1": "ann"}, "job_id": {"2": "Ops"}}),
])
def test_list_labels_cover_the_page_only(client, prefix, headers, first):
    assert client.get(f"{prefix}/items?limit=1", headers=headers).json()["labels"] == first
    labels = client.get(f"{prefix}/items", headers=headers).json()["labels"]
    assert labels["job_id"] == {"1": "Dev", "2": "Ops"}  # 99 unknown: no entry
    assert labels["skill_key"] == {"py": "Python"}
    assert "ghost_id" not in labels and "secret_id" not in labels and "hidden_id" not in labels


def test_user_labels_and_tombstone(client):
    labels = client.get("/records/items", headers=ADMIN).json()["labels"]
    assert labels["user_id"] == {"1": "ann", "0": TOMBSTONE_LABEL}


def test_single_row_has_labels(client):
    row = client.get("/records/items/1", headers=ADMIN).json()
    assert row["labels"] == {"user_id": {"1": "ann"}, "job_id": {"1": "Dev"}, "skill_key": {"py": "Python"}}
    assert client.get("/records/items/1", headers=ME).json()["labels"]["job_id"] == {"1": "Dev"}
    assert "secret_id" not in row["labels"]


def test_missing_users_table_is_skipped():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Item.__table__])
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(records_router([spec()]), prefix="/records")
    with engine.begin() as conn:
        conn.execute(Item.__table__.insert(), [{"user_id": 1, "job_id": 1}])
    with TestClient(app) as c:
        r = c.get("/records/items", headers=ADMIN)
        assert r.status_code == 200 and "labels" not in r.json()
        assert c.get("/records/items/1", headers=ADMIN).status_code == 200
