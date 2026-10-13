import pytest
from sqlalchemy import inspect, select

from app.account_events import on_user_deleted, on_user_renamed
from app.limits import UserRateLimiter
from app.models import Measurement
from tests.conftest import auth_cookie

FULL = {"symmetry": 87, "eye": 90, "nose": 80, "mouth": 85, "ear": 70, "angle": 12.5}


def post(client, headers, body=None, **kw):
    return client.post("/measurements", json=FULL if body is None else body, headers=headers, **kw)


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_returns_contract_shape(client, alice):
    response = post(client, alice)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "createdAt", "symmetry", "eye", "nose", "mouth", "ear", "angle"}
    assert {k: body[k] for k in FULL} == FULL
    assert isinstance(body["id"], int) and "T" in body["createdAt"]


def test_optional_fields_default_to_null(client, alice):
    body = post(client, alice, {"symmetry": 0}).json()
    assert body["eye"] is body["nose"] is body["mouth"] is body["ear"] is body["angle"] is None


def test_list_newest_first_with_limit(client, alice):
    ids = [post(client, alice, {"symmetry": n}).json()["id"] for n in range(5)]
    rows = client.get("/measurements", headers=alice).json()
    assert [r["id"] for r in rows] == ids[::-1]
    assert len(client.get("/measurements?limit=2", headers=alice).json()) == 2


@pytest.mark.parametrize("limit", [0, 201, "x"])
def test_list_limit_validation(client, alice, limit):
    assert client.get(f"/measurements?limit={limit}", headers=alice).status_code == 422


def test_isolation_between_users(client, alice, bob):
    mine = post(client, alice).json()["id"]
    post(client, bob, {"symmetry": 1})
    assert [r["symmetry"] for r in client.get("/measurements", headers=bob).json()] == [1]
    assert client.delete(f"/measurements/{mine}", headers=bob).status_code == 404
    assert len(client.get("/measurements", headers=alice).json()) == 1
    client.delete("/measurements", headers=bob)
    assert len(client.get("/measurements", headers=alice).json()) == 1


def test_delete_one_and_unknown_vs_foreign_same_body(client, alice, bob):
    mid = post(client, alice).json()["id"]
    foreign = client.delete(f"/measurements/{mid}", headers=bob)
    unknown = client.delete("/measurements/9999", headers=bob)
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    assert client.delete(f"/measurements/{mid}", headers=alice).status_code == 204
    assert client.delete(f"/measurements/{mid}", headers=alice).status_code == 404


def test_delete_all_own_rows(client, alice):
    post(client, alice)
    post(client, alice)
    response = client.delete("/measurements", headers=alice)
    assert response.status_code == 204 and response.content == b""
    assert client.get("/measurements", headers=alice).json() == []
    assert client.delete("/measurements", headers=alice).status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"symmetry": -1},
        {"symmetry": 101},
        {"symmetry": 50.5},
        {"symmetry": "50"},
        {"symmetry": True},
        {"symmetry": 50, "eye": 101},
        {"symmetry": 50, "ear": -3},
        {"symmetry": 50, "angle": -0.1},
        {"symmetry": 50, "angle": 90.1},
        {"symmetry": 50, "username": "alice"},
        {"symmetry": 50, "landmarks": [[0, 0]]},
    ],
)
def test_validation_rejects(client, alice, body):
    assert post(client, alice, body).status_code == 422


@pytest.mark.parametrize("body", [{"symmetry": 0, "angle": 0}, {"symmetry": 100, "eye": 100, "angle": 90}])
def test_validation_accepts_edges(client, alice, body):
    assert post(client, alice, body).status_code == 201


def test_cap_200_drops_oldest(client, alice):
    ids = []
    for n in range(202):
        if n and n % 25 == 0:
            client.app.state.limiter = UserRateLimiter()  # keep the rate limit out of the way
        ids.append(post(client, alice, {"symmetry": n % 101}).json()["id"])
    rows = client.get("/measurements?limit=200", headers=alice).json()
    assert len(rows) == 200
    assert [r["id"] for r in rows] == ids[2:][::-1]


def test_cap_does_not_touch_other_users(client, alice, bob):
    post(client, bob)
    client.app.state.limiter = UserRateLimiter(max_events=1000)
    for _ in range(201):
        post(client, alice)
    assert len(client.get("/measurements", headers=bob).json()) == 1


def test_rate_limit_30_per_minute(client, alice, bob):
    codes = [post(client, alice).status_code for _ in range(31)]
    assert codes == [201] * 30 + [429]
    assert "detail" in post(client, alice).json()
    assert post(client, bob).status_code == 201


def test_rate_limiter_window_and_prune():
    now = [0.0]
    limiter = UserRateLimiter(max_events=1, window=10, clock=lambda: now[0])
    assert limiter.allow(1) and not limiter.allow(1)
    now[0] = 11
    assert limiter.allow(1)
    for uid in range(2, 1100):
        limiter.allow(uid)
    now[0] = 100
    assert limiter.allow(5000)
    assert len(limiter._events) < 10


def test_auth_required(client):
    assert client.get("/measurements").status_code == 401
    assert client.post("/measurements", json=FULL).status_code == 401
    assert client.delete("/measurements").status_code == 401
    assert client.delete("/measurements/1").status_code == 401
    assert client.get("/measurements", headers={"Cookie": "sn_token=garbage"}).status_code == 401


def test_origin_check_on_unsafe_routes(client, alice):
    evil = {**alice, "Origin": "https://evil.example"}
    mid = post(client, alice).json()["id"]
    for response in (
        client.post("/measurements", json=FULL, headers=evil),
        client.delete(f"/measurements/{mid}", headers=evil),
        client.delete("/measurements", headers=evil),
    ):
        assert response.status_code == 403
        assert response.json() == {"detail": "Origin not allowed"}
    good = {**alice, "Origin": "http://localhost:8080"}
    assert client.post("/measurements", json=FULL, headers=good).status_code == 201
    assert client.get("/measurements", headers=evil).status_code == 200  # safe method


def test_origin_allow_list_from_env(client, alice, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    assert client.post("/measurements", json=FULL, headers={**alice, "Origin": "https://b.example"}).status_code == 201


def test_no_pii_columns(client):
    columns = {c["name"] for c in inspect(client.app.state.session_factory.kw["bind"]).get_columns("measurements")}
    assert columns == {"id", "user_id", "created_at", "symmetry", "eye", "nose", "mouth", "ear", "angle"}


def test_account_deleted_event_is_idempotent(client, alice, bob):
    post(client, alice)
    post(client, bob)
    with client.app.state.session_factory() as db:
        on_user_deleted(db, 1)
        on_user_deleted(db, 1)
        on_user_deleted(db, 0)
        on_user_deleted(db, -5)
        db.commit()
        assert [m.user_id for m in db.scalars(select(Measurement))] == [2]


def test_account_renamed_is_noop(client, alice):
    post(client, alice)
    with client.app.state.session_factory() as db:
        on_user_renamed(db, 1, "newname")
        db.commit()
        assert db.scalar(select(Measurement.symmetry)) == 87


def test_other_user_cookie_helper():
    assert auth_cookie(3, "c")["Cookie"].startswith("sn_token=")
