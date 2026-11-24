"""The account `system`: the voice of the chat's lines about its rooms. It exists, owns the name, and nobody signs in as it."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.center.models import User
from api.center.system_user import SYSTEM_KIND, SYSTEM_USER_ID, SYSTEM_USERNAME, ensure_system_user
from tests.center.conftest import create_app
from tests.center.helpers import register


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SYSTEM_USER", "1")
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def test_the_account_is_made_when_center_starts_and_is_a_user_of_its_own_kind(client):
    with client.app.state.session_factory() as db:
        user = db.get(User, SYSTEM_USER_ID)
        assert (user.id, user.username, user.kind, user.group) == (-1, SYSTEM_USERNAME, SYSTEM_KIND, "user")
        assert user.has_password is False and user.email is None and user.phone is None


def test_making_it_again_changes_nothing(client):
    with client.app.state.session_factory() as db:
        first = ensure_system_user(db)
        second = ensure_system_user(db)
        assert first.id == second.id == SYSTEM_USER_ID
        assert len(list(db.scalars(select(User).where(User.username == SYSTEM_USERNAME)))) == 1


def test_nobody_registers_under_the_name(client):
    for name in ("system", "SYSTEM", "System"):
        assert client.post("/auth/register", json={"username": name, "password": "S3cret-Pass"}).status_code == 409


@pytest.mark.parametrize("password", ["", "!", "S3cret-Pass", "x" * 200])
def test_nobody_signs_in_as_it(client, password):
    response = client.post("/auth/login", json={"username": "system", "password": password})
    assert response.status_code in (401, 403, 422) and "sn_token" not in response.headers.get("set-cookie", "")


def test_the_ids_of_people_never_reach_it(client):
    register(client)
    with client.app.state.session_factory() as db:
        people = [u.id for u in db.scalars(select(User).where(User.kind == "human"))]
        assert people and min(people) >= 1 and SYSTEM_USER_ID not in people


def test_a_row_that_took_the_name_first_keeps_it_and_the_account_is_not_made(client):
    """Registering cannot take the name (it is a reserved one); an older database might already hold it."""
    from api.center.passwords import NO_PASSWORD

    with client.app.state.session_factory() as db:
        db.delete(db.get(User, SYSTEM_USER_ID))
        db.commit()
        db.add(User(username="system", password_hash=NO_PASSWORD))
        db.commit()
        assert ensure_system_user(db) is None
        assert db.get(User, SYSTEM_USER_ID) is None
