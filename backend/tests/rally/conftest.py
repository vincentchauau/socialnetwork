import os

import pytest
from fastapi.testclient import TestClient

from sn_shared.testing import add_person, install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from api.rally.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    install_test_keys(monkeypatch)
    monkeypatch.setenv("RALLY_UPLOAD_DIR", str(tmp_path / "rally"))


@pytest.fixture
def client():
    app = create_app("sqlite://")
    add_person(app.state.session_factory, 1, "alice")
    add_person(app.state.session_factory, 2, "bob")
    with TestClient(app) as test_client:
        yield test_client
    app.state.session_factory.kw["bind"].dispose()  # close the in-memory database, so no connection outlives the test


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


ALICE = auth_cookie(1, "alice")
BOB = auth_cookie(2, "bob")
