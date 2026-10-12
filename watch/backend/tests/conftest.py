import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), ".uploads"))

from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token

MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + bytes(range(256)) * 4
WEBM_BYTES = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01" + bytes(range(256)) * 4


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MAX_VIDEO_MB", "1")


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    return tmp_path / "uploads"


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


def upload(
    client: TestClient,
    *,
    user_id: int = 1,
    username: str = "alice",
    title: str = "My clip",
    content: bytes = MP4_BYTES,
    filename: str = "clip.mp4",
    rights: str = "true",
    extra: dict | None = None,
    tags: list[str] | None = None,
):
    data: dict = {"title": title, "rights_confirmed": rights, **(extra or {})}
    if tags is not None:
        data["tags"] = tags
    return client.post(
        "/videos",
        headers=auth_cookie(user_id, username),
        data=data,
        files={"file": (filename, content, "application/octet-stream")},
    )
