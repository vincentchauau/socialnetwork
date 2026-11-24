"""The whole backend in one process: every module under its own path, each with its own database."""

import pytest
from fastapi.testclient import TestClient
from sn_shared.testing import install_test_keys

install_test_keys()

from api.main import MODULES, create_app  # noqa: E402

ORIGIN = {"Origin": "http://localhost:8080"}


@pytest.fixture
def backend(tmp_path, monkeypatch):
    install_test_keys(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8080")
    for name in ("REDIS_URL", "SMTP_HOST", "BIOMETRICS_ENABLED", "GOOGLE_CLIENT_ID", "AGENT_SECRET", "AGENT_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("FILE_DATA_DIR", str(tmp_path / "file"))
    monkeypatch.setenv("DATABASE_DATA_DIR", str(tmp_path / "database"))
    urls = {name: f"sqlite:///{tmp_path / (name + '.db')}" for name in MODULES}
    with TestClient(create_app(urls)) as client:
        yield client


def test_every_module_answers_under_its_own_path_and_the_backend_itself_is_healthy(backend):
    assert backend.get("/health").json() == {"status": "ok"}
    assert set(backend.app.state.modules) == set(MODULES)  # every module of `api.main`: the one list the backend itself is made from
    for name in MODULES:
        assert backend.get(f"/{name}/health").json()["status"] == "ok", name


def test_a_person_who_signs_up_at_the_center_is_known_to_the_other_modules_by_the_same_cookie(backend):
    made = backend.post("/center/auth/register", json={"username": "alice", "password": "S3cret-Pass-1"}, headers=ORIGIN)
    assert made.status_code == 201, made.text
    assert backend.get("/center/auth/me").json()["username"] == "alice"
    assert backend.get("/market/products").status_code == 200  # the cookie of the center is enough for the market
    assert backend.get("/job/jobs").status_code == 200
    assert backend.get("/chat/rooms", params={"scope": "public"}).status_code == 200
    backend.cookies.clear()
    assert backend.get("/market/products").status_code == 401


def test_each_module_keeps_its_own_database(backend):
    names = {name: str(module.state.session_factory.kw["bind"].url.database) for name, module in backend.app.state.modules.items()}
    assert len(set(names.values())) == len(MODULES)


def test_the_routes_of_a_module_stay_in_that_module(backend):
    backend.post("/center/auth/register", json={"username": "bob", "password": "S3cret-Pass-1"}, headers=ORIGIN)
    assert backend.get("/market/courses").status_code == 404
    assert backend.get("/job/jobs").status_code == 200
    assert backend.get("/nowhere").status_code == 404
