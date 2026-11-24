import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.admincrud import TableSpec, records_router
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class Pic(Base):
    __tablename__ = "pics"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column()
    image_name: Mapped[str] = mapped_column(String(50))
    url: Mapped[str | None] = mapped_column(String(50), nullable=True)


MEDIA = {"image_name": {"kind": "image", "preview": "/p/{id}/thumb", "replace": "/p/{id}/image", "accept": "image/*"}, "url": {"preview": "@self"}}


def make():
    return TableSpec(Pic, owner="user_id", media=MEDIA, create_via="/api/p", create_label="Upload")


def client_for(_ops=None):
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.include_router(records_router([make()]), prefix="/records")
    return TestClient(app)


ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}
ME = {"Cookie": f"{COOKIE_NAME}={create_token(1, 'ann')}"}


def cols(client, prefix, headers):
    table = client.get(f"{prefix}/tables", headers=headers).json()[0]
    return table, {c["name"]: c for c in table["columns"]}


def test_media_and_create_via_described_in_admin():
    table, by = cols(client_for("RUD"), "/records", ADMIN)
    assert by["image_name"]["media"] == MEDIA["image_name"]
    assert by["url"]["media"] == {"kind": "image", "preview": "@self"}
    assert "media" not in by["id"]
    assert table["create_via"] == "/api/p" and table["create_label"] == "Upload"


def test_data_hides_replace_without_update():
    _, by = cols(client_for("RD"), "/records", ME)
    assert by["image_name"]["media"] == {"kind": "image", "preview": "/p/{id}/thumb", "accept": "image/*"}
    _, by = cols(client_for("RUD"), "/records", ME)
    assert "replace" not in by["image_name"]["media"]  # a person never gets the replace address
    _, by = cols(client_for("RUD"), "/records", ADMIN)
    assert by["image_name"]["media"]["replace"] == "/p/{id}/image"


def test_plain_table_has_no_extra_fields():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine)
    app.include_router(records_router([TableSpec(Pic)]), prefix="/records")
    table = TestClient(app).get("/records/tables", headers=ADMIN).json()[0]
    assert "create_via" not in table and all("media" not in c for c in table["columns"])


@pytest.mark.parametrize("kwargs", [
    {"media": {"nope": {"preview": "/x"}}},
    {"media": {"url": {"kind": "pdf"}}},
    {"media": {"url": {"preview": "/x", "bogus": "1"}}},
    {"media": {"url": {"preview": "/x/{ghost}"}}},
    {"media": {"url": {"preview": "@self", "replace": "/x"}}},
    {"create_label": "x"},
])
def test_invalid_declarations_rejected(kwargs):
    with pytest.raises(ValueError):
        TableSpec(Pic, **kwargs)
