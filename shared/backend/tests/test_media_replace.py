import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from sn_shared import COOKIE_NAME, create_token
from sn_shared.db import make_engine
from sn_shared.media import Inspected, MediaRejected, add_replace_route
from sn_shared.deps import get_current_user
from sn_shared.testing import install_test_keys

install_test_keys()


class Base(DeclarativeBase):
    pass


class Doc(Base):
    __tablename__ = "docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column()
    ref: Mapped[str] = mapped_column(String(50))
    size: Mapped[int] = mapped_column(default=0)


def build(fail_commit=False):
    files: dict[str, bytes] = {"a0": b"old"}
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        s.add(Doc(id=1, user_id=1, ref="a0"))
        s.commit()
    counter = iter(range(1, 100))

    def get_db():
        with factory() as s:
            if fail_commit:
                s.commit = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
            yield s

    def inspect(raw: bytes, file: UploadFile) -> Inspected:
        if raw.startswith(b"BAD"):
            raise MediaRejected(422, "bad content")
        return Inspected(raw, {"size": len(raw)})

    def write(row, data, updates):
        name = f"a{next(counter)}"
        files[name] = data
        return {"ref": name}

    app = FastAPI()
    add_replace_route(app, "/docs/{item_id}/file", model=Doc, get_db=get_db, get_user=get_current_user, inspect=inspect,
                      write=write, delete=lambda refs: files.pop(refs["ref"], None), ref_columns=("ref",),
                      respond=lambda db, row, user: {"id": row.id, "ref": row.ref, "size": row.size},
                      max_bytes=10, allowed_types=["application/pdf", "image/*"])
    return TestClient(app), files


def tok(uid, group="user"):
    return {"Cookie": f"{COOKIE_NAME}={create_token(uid, 'u', group=group)}"}


def put(c, data=b"new", ctype="application/pdf", headers=None, item=1):
    return c.put(f"/docs/{item}/file", files={"file": ("f", data, ctype)}, headers=headers or tok(1))


def test_owner_replaces_and_old_file_removed():
    c, files = build()
    r = put(c)
    assert r.status_code == 200 and r.json() == {"id": 1, "ref": "a1", "size": 3}
    assert files == {"a1": b"new"}


def test_admin_allowed_other_user_404():
    c, files = build()
    assert put(c, headers=tok(2)).status_code == 404
    assert files == {"a0": b"old"}
    assert put(c, headers=tok(9, "admin")).status_code == 200
    assert put(c, item=5).status_code == 404


@pytest.mark.parametrize("data,ctype,code", [(b"x", "text/plain", 415), (b"x" * 11, "image/png", 413), (b"BADx", "image/png", 422)])
def test_rejections_leave_files(data, ctype, code):
    c, files = build()
    assert put(c, data, ctype).status_code == code
    assert files == {"a0": b"old"}


def test_unauthenticated():
    c, _ = build()
    assert c.put("/docs/1/file", files={"file": ("f", b"x", "image/png")}).status_code == 401


def test_failed_commit_removes_new_file_keeps_old():
    c, files = build(fail_commit=True)
    with pytest.raises(RuntimeError):
        put(c)
    assert files == {"a0": b"old"}
