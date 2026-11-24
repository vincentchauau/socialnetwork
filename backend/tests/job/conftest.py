import os

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
from sn_shared.testing import add_person, install_test_keys  # noqa: E402

install_test_keys()
os.environ.setdefault("DATABASE_URL", "sqlite://")

from api.job.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token


_people: dict[int, str] = {}


def _seed_people(test_client) -> None:
    """Names are read from `users` of center: whoever has a cookie in a test is a person there."""
    for user_id, username in list(_people.items()):
        add_person(test_client.app.state.session_factory, user_id, username)


def _seeding(test_client):
    send = test_client.request

    def request(*args, **kwargs):
        _seed_people(test_client)
        return send(*args, **kwargs)

    test_client.request = request
    return test_client


@pytest.fixture(autouse=True)
def env(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    with TestClient(create_app("sqlite://")) as test_client:
        yield _seeding(test_client)


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    _people[user_id] = username
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
