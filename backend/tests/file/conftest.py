import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from api.file.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    install_test_keys(monkeypatch)
    monkeypatch.setenv("FILE_DATA_DIR", str(tmp_path / "file"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice", group: str = "user") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username, group=group)}"}


@pytest.fixture
def alice() -> dict[str, str]:
    return auth_cookie(1, "alice")


@pytest.fixture
def bob() -> dict[str, str]:
    return auth_cookie(2, "bob")


@pytest.fixture
def admin() -> dict[str, str]:
    return auth_cookie(9, "root", group="admin")
