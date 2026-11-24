"""Files of a table's rows: stored at `{root}/{database}/{table}/{column}/{row_id}/{file}`, served to whoever may see the row."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared import recordfiles
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.db import make_engine
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(40))
    cover: Mapped[str | None] = mapped_column(String(255), nullable=True)


def who(user_id, group="user"):
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, 'u', group=group)}"}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(recordfiles.ROOT_ENV, str(tmp_path / "records"))
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    mount_crud(app, [TableSpec(Photo, owner="owner_id", media={"cover": {"kind": "image", "preview": "files/cover"}})], database="market")
    with engine.begin() as conn:
        conn.execute(Photo.__table__.insert(), [{"owner_id": 1, "title": "mine"}, {"owner_id": 2, "title": "bobs"}])
    with TestClient(app) as c:
        yield c


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_an_admin_keeps_the_picture_in_the_cells_folder_and_it_is_listed_and_served(client, tmp_path):
    sent = client.post("/records/photos/1/files/cover", files={"file": ("cat.png", PNG, "image/png")}, headers=who(9, "admin"))
    assert sent.status_code == 200, sent.text
    assert sent.json()["cover"] == "market/photos/cover/1"
    assert (tmp_path / "records" / "market" / "photos" / "cover" / "1" / "cat.png").read_bytes() == PNG
    listed = client.get("/records/photos/1/files/cover", headers=who(1)).json()["files"]
    assert [(f["name"], f["kind"]) for f in listed] == [("cat.png", "image")]
    served = client.get(listed[0]["url"], headers=who(1))
    assert served.status_code == 200 and served.content == PNG and served.headers["content-type"] == "image/png"


def test_a_person_cannot_upload_and_a_wrong_kind_is_refused(client):
    assert client.post("/records/photos/1/files/cover", files={"file": ("cat.png", PNG, "image/png")}, headers=who(1)).status_code == 403
    refused = client.post("/records/photos/1/files/cover", files={"file": ("notes.txt", b"x", "text/plain")}, headers=who(9, "admin"))
    assert refused.status_code == 422


def test_a_cell_holds_many_files_and_a_file_with_the_same_name_replaces_its_old_one(client, tmp_path):
    client.post("/records/photos/1/files/cover", files={"file": ("a.png", PNG, "image/png")}, headers=who(9, "admin"))
    client.post("/records/photos/1/files/cover", files={"file": ("b.png", PNG, "image/png")}, headers=who(9, "admin"))
    client.post("/records/photos/1/files/cover", files={"file": ("a.png", PNG + b"x", "image/png")}, headers=who(9, "admin"))
    names = [f["name"] for f in client.get("/records/photos/1/files/cover", headers=who(9, "admin")).json()["files"]]
    assert names == ["a.png", "b.png"]


def test_a_person_cannot_remove_a_file_and_an_admin_can(client):
    client.post("/records/photos/1/files/cover", files={"file": ("a.png", PNG, "image/png")}, headers=who(9, "admin"))
    assert client.delete("/records/photos/1/files/cover/a.png", headers=who(1)).status_code == 403
    assert client.delete("/records/photos/1/files/cover/a.png", headers=who(9, "admin")).status_code == 204
    assert client.get("/records/photos/1/files/cover", headers=who(9, "admin")).json()["files"] == []


def test_names_cannot_leave_their_folder():
    assert recordfiles.clean_name("../../etc/passwd.png") == "passwd.png"
    assert "/" not in recordfiles.clean_name("a/b\c.png")
    with pytest.raises(recordfiles.FileRefused):
        recordfiles.check("image", "x.png", 20 * 1024 * 1024)


def workbook(rows: list[list]) -> bytes:
    import io

    from openpyxl import Workbook

    book = Workbook()
    for row in rows:
        book.active.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_an_admin_imports_an_excel_file_as_rows_and_a_person_cannot(client):
    data = workbook([["title", "owner_id"], ["first", 1], [None, None], ["second", 1]])
    refused = client.post("/records/photos/import", files={"file": ("rows.xlsx", data, "application/octet-stream")}, headers=who(1))
    assert refused.status_code == 403
    done = client.post("/records/photos/import", files={"file": ("rows.xlsx", data, "application/octet-stream")}, headers=who(9, "admin"))
    assert done.status_code == 200, done.text
    assert done.json()["created"] == 2
    assert [r["status"] for r in done.json()["results"]] == ["created", "created"]


def test_the_plan_names_the_rows_that_already_exist_and_overwrite_is_a_choice(client):
    data = workbook([["id", "title", "owner_id"], [1, "changed", 1], [77, "new", 1]])
    plan = client.post("/records/photos/import-plan", files={"file": ("data.xlsx", data, "application/octet-stream")}, headers=who(9, "admin")).json()
    assert (plan["new"], plan["existing"]) == (1, 1)
    skipped = client.post("/records/photos/import", files={"file": ("data.xlsx", data, "application/octet-stream")}, data={"overwrite": "false"}, headers=who(9, "admin")).json()
    assert [r["status"] for r in skipped["results"]] == ["skipped", "created"]
    assert client.get("/records/photos/1", headers=who(9, "admin")).json()["title"] == "mine"
    over = client.post("/records/photos/import", files={"file": ("data.xlsx", data, "application/octet-stream")}, data={"overwrite": "true"}, headers=who(9, "admin")).json()
    assert [r["status"] for r in over["results"]] == ["updated", "updated"]  # 77 was created by the run before
    assert client.get("/records/photos/1", headers=who(9, "admin")).json()["title"] == "changed"


def test_only_xlsx_files_are_imported(client):
    response = client.post("/records/photos/import", files={"file": ("rows.csv", b"title\nx\n", "text/csv")}, headers=who(9, "admin"))
    assert response.status_code == 422


def test_a_file_over_the_size_limit_is_refused_and_its_bytes_are_never_saved(client, tmp_path):
    too_big = b"\x89PNG" + b"0" * (recordfiles.LIMITS["image"] + 1)
    refused = client.post("/records/photos/1/files/cover", files={"file": ("big.png", too_big, "image/png")}, headers=who(9, "admin"))
    assert refused.status_code == 422
    assert "at most" in refused.json()["detail"]
    assert client.get("/records/photos/1/files/cover", headers=who(9, "admin")).json()["files"] == []
