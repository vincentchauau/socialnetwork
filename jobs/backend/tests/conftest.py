import os

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
from sn_shared.testing import install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token


@pytest.fixture(autouse=True)
def env(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


ALICE = auth_cookie(1, "alice")
BOB = auth_cookie(2, "bob")
CAROL = auth_cookie(3, "carol")


def job_body(**overrides) -> dict:
    body = {
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Berlin",
        "remote": False,
        "employment_type": "full_time",
        "description": "Build services.\nSecond line.",
        "tags": ["python", "fastapi"],
    }
    return {**body, **overrides}


def post_job(client, headers=ALICE, **overrides) -> dict:
    response = client.post("/jobs", json=job_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()
