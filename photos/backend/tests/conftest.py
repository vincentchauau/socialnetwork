import io
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# create_app() runs at import time and needs these.
from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="photos-import-"))

from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    install_test_keys(monkeypatch)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


ALICE = auth_cookie(1, "alice")
BOB = auth_cookie(2, "bob")


def make_image(fmt: str = "PNG", size: tuple[int, int] = (64, 48), mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, "red").save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, headers=ALICE, data: bytes | None = None, caption: str | None = None, name="p.png"):
    files = {"file": (name, data if data is not None else make_image(), "application/octet-stream")}
    form = {"caption": caption} if caption is not None else {}
    return client.post("/photos", files=files, data=form, headers=headers)
