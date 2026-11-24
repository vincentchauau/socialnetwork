"""The two gates of every route: `require_groups` (letters per group, by HTTP method) and `require_users`."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sn_shared.deps import GROUP_ADMIN, GROUP_MODERATOR, GROUP_USER, GROUPS, action_of, require_groups, require_users
from sn_shared.security import COOKIE_NAME, create_token
from sn_shared.testing import install_test_keys

install_test_keys()


def cookie(group: str, user_id: int = 5) -> dict:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, 'u', 300, group=group)}"}


def make_app(**groups) -> TestClient:
    app = FastAPI()
    gate = [Depends(require_groups(**groups)), Depends(require_users())]

    @app.get("/x", dependencies=gate)
    def read() -> dict:
        return {"ok": True}

    @app.post("/x", dependencies=gate)
    def create() -> dict:
        return {"ok": True}

    @app.patch("/x", dependencies=gate)
    def update() -> dict:
        return {"ok": True}

    @app.delete("/x", dependencies=gate)
    def remove() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_groups_are_the_three_platform_groups():
    assert GROUPS == ("user", "moderator", "admin")


@pytest.mark.parametrize("method,letter", [("GET", "R"), ("POST", "C"), ("PATCH", "U"), ("DELETE", "D")])
def test_each_method_is_one_letter(method, letter):
    class Conn:
        pass

    conn = Conn()
    conn.method = method
    assert action_of(conn) == letter


def test_a_moderator_is_cru_on_every_route():
    client = make_app(admin=True, moderator=True)
    assert client.get("/x", headers=cookie(GROUP_MODERATOR)).status_code == 200
    assert client.post("/x", headers=cookie(GROUP_MODERATOR)).status_code == 200
    assert client.patch("/x", headers=cookie(GROUP_MODERATOR)).status_code == 200
    assert client.delete("/x", headers=cookie(GROUP_MODERATOR)).status_code == 403
    assert client.delete("/x", headers=cookie(GROUP_USER)).status_code == 403
    assert client.delete("/x", headers=cookie(GROUP_ADMIN)).status_code == 200


def test_anonymous_is_refused_with_401():
    client = make_app(admin=True)
    assert client.get("/x").status_code == 401


def test_a_group_with_no_letters_is_refused():
    client = make_app(admin=True)
    assert client.get("/x", headers=cookie(GROUP_USER)).status_code == 403


def test_require_users_narrows_the_call_to_the_given_ids():
    app = FastAPI()

    @app.get("/y", dependencies=[Depends(require_groups(admin=True, user=True)), Depends(require_users(7))])
    def only_seven() -> dict:
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/y", headers=cookie(GROUP_USER, user_id=7)).status_code == 200
    assert client.get("/y", headers=cookie(GROUP_USER, user_id=8)).status_code == 403


def test_both_gates_must_pass():
    app = FastAPI()

    @app.get("/z", dependencies=[Depends(require_groups(admin=True)), Depends(require_users(7))])
    def both() -> dict:
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/z", headers=cookie(GROUP_ADMIN, user_id=8)).status_code == 403
    assert client.get("/z", headers=cookie(GROUP_ADMIN, user_id=7)).status_code == 200
    assert client.get("/z", headers=cookie(GROUP_USER, user_id=7)).status_code == 403


def test_the_attributes_carry_the_rule():
    gate = require_groups(admin=True, moderator=True, user=True)
    assert gate.access_groups == {"admin", "moderator", "user"}
    assert require_users().access_users == frozenset()
    assert require_groups(public=True).public is True
