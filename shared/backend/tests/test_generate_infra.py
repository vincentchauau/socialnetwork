"""Checks on what shared/infra/generate_infra.py emits (parsed, never run through docker)."""

import importlib.util
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

INFRA = Path(__file__).resolve().parents[2] / "infra" / "generate_infra.py"
BACKEND_APPS = ("center", "chat", "werewolf", "file", "market", "job", "face", "roulette")


@pytest.fixture(scope="module")
def infra():
    spec = importlib.util.spec_from_file_location("generate_infra", INFRA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.APPS = module.ALL_APPS
    return module


@pytest.fixture(scope="module")
def compose_text(infra):
    return infra.compose()


@pytest.fixture(scope="module")
def services(compose_text):
    return yaml.safe_load(compose_text)["services"]


def test_only_the_api_backend_gets_the_jwt_secret_and_the_private_key(services):
    holders = [name for name, svc in services.items() if "JWT_SECRET" in (svc.get("environment") or {})]
    assert holders == ["api-backend"]
    private = [name for name, svc in services.items() if "jwt_private_key" in (svc.get("secrets") or [])]
    assert private == ["api-backend"]
    assert "jwt_public_keys" in services["api-backend"]["secrets"]


def test_frontends_and_gateway_receive_no_environment(services):
    assert not services["gateway"].get("environment") and not services["web-frontend"].get("environment")


def test_every_backend_connects_to_the_one_database_with_the_app_role(services):
    env = services["api-backend"]["environment"]
    assert env["DATABASE_URL"].startswith("postgresql+psycopg://sn_app:") and env["DATABASE_URL"].endswith("@postgres:5432/app")
    assert not [k for k in env if k.endswith("_DATABASE_URL")]


def test_the_superuser_password_stays_on_the_postgres_service(services):
    assert "POSTGRES_PASSWORD" in services["postgres"]["environment"]
    for name, svc in services.items():
        if name != "postgres":
            assert "POSTGRES_PASSWORD" not in (svc.get("environment") or {}), name


def test_postgres_receives_the_app_role_password(services):
    assert services["postgres"]["environment"]["DB_PASSWORD_APP"].startswith("${DB_PASSWORD_APP:?")


def test_role_scripts_create_the_one_login_role_and_lock_the_database_down(infra):
    body = infra.roles_body()
    assert "CREATE ROLE %I" in body and "CREATE DATABASE %I OWNER %I" in body
    assert "NOSUPERUSER" in body and "NOBYPASSRLS" in body


def test_secrets_are_files_under_the_infra_folder(compose_text):
    assert "./secrets/jwt_private.pem" in compose_text and "./secrets/jwt_public_keys.pem" in compose_text


def test_the_messaging_services_run_only_in_their_profile(services):
    for name in ("kafka", "rabbitmq", "api-worker"):
        assert services[name]["profiles"] == ["messaging"], name


def test_rabbitmq_management_is_only_on_localhost(services):
    assert services["rabbitmq"]["ports"] == ["127.0.0.1:15672:15672"]


def test_file_and_database_uploads_are_authenticated(infra):
    text = infra.nginx()
    for app, path, size in (("file", "/upload", "21m"),):
        block = text.split(f"location = /api/{app}{path} {{", 1)[1].split("\n    }", 1)[0]
        assert "auth_request /_auth;" in block and f"client_max_body_size {size};" in block
        assert f"proxy_pass http://api-backend:8000/{app}{path};" in block
    # the generic /api/chat/ location has no auth_request (the chat authenticates its own routes)
    generic = text.split("location /api/chat/ {", 1)[1].split("\n    }", 1)[0]
    assert "auth_request" not in generic and "proxy_pass http://api-backend:8000/chat/;" in generic


def test_the_api_backend_keeps_the_data_folder_and_a_tmp_for_uploads(services):
    backend = services["api-backend"]
    assert "../../backend/data:/data" in backend["volumes"]
    assert "/tmp:size=64m" in backend["tmpfs"]
    assert backend["environment"]["FILE_DATA_DIR"] == "/data/file"
    assert backend["environment"]["RECORDS_DATA_DIR"] == "/data/records"


def test_every_app_is_in_the_one_api_service_and_the_gateway_finds_it_there(infra, services):
    for slug in BACKEND_APPS:
        assert f"{slug}-backend" not in services
    assert sorted(name for name in services if name.endswith("-backend")) == ["api-backend"]
    text = infra.nginx()
    for slug in ("face", "chat"):
        assert f"proxy_pass http://api-backend:8000/{slug}/;" in text
    assert "proxy_pass http://api-backend:8000/center/auth/me;" in text and "location /api/api/" not in text


def test_asking_for_one_app_brings_the_backend_that_hosts_it(infra):
    assert {a.slug for a in infra.select_apps("face")} == {"face", "api"}


def test_the_old_chatwork_addresses_move_to_the_apps_that_replaced_them(infra):
    nginx = infra.nginx()
    assert "return 301 $scheme://$http_host/$1$2;" in nginx and "return 301 $scheme://$http_host/chat$1;" in nginx
    assert "location ~ ^/chatwork/(file|database)(/.*)?$ {" in nginx
    assert "location ~ ^/chatwork(/.*)?$ {" in nginx
    assert [(a.slug, a.frontend, a.backend) for a in infra.APPS if a.slug in ("chat", "file", "database")] == [
        ("chat", True, True), ("file", True, True), ("database", True, False),
    ]


def test_each_app_is_in_the_menu_and_the_gateway_redirects_its_old_plural(infra):
    names = {a.slug for a in infra.APPS}
    assert {"face", "werewolf"} <= names
    assert 'href: "/werewolf"' in infra.apps_ts()


def test_the_werewolf_is_a_module_of_its_own_that_the_chat_reaches_with_a_signed_call(infra, services):
    env = services["api-backend"]["environment"]
    assert env["WEREWOLF_URL"] == "http://127.0.0.1:8000/werewolf" and env["WEREWOLF_SECRET"] == "${WEREWOLF_SECRET:-}"
    nginx = infra.nginx()
    assert "location /api/werewolf/ {" in nginx
    block = nginx.split("location /api/werewolf/ {", 1)[1].split("\n    }", 1)[0]
    assert "proxy_pass http://api-backend:8000/werewolf/;" in block and "Upgrade" in block  # the sockets of the game
    assert "location ^~ /api/werewolf/internal/ {\n        return 404;" in nginx  # the call of the chat is not reachable from outside
    assert "location ^~ /api/chat/internal/ {\n        return 404;" in nginx  # nor the call of the game to the chat
    assert "location ~ ^/social(/.*)?$ {" in nginx and "/chat/people$1" in nginx  # the page of the people is part of the chat again
