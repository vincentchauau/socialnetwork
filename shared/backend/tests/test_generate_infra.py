"""Checks on what shared/infra/generate_infra.py emits (parsed, never run through docker)."""

import importlib.util
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

INFRA = Path(__file__).resolve().parents[2] / "infra" / "generate_infra.py"


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


def test_only_center_backend_gets_jwt_secret_and_the_private_key(services, compose_text):
    holders = [name for name, svc in services.items() if "JWT_SECRET" in (svc.get("environment") or {})]
    assert holders == ["center-backend"]
    assert "jwt_private_key" in services["center-backend"]["secrets"]
    for name, svc in services.items():
        if name != "center-backend":
            assert "jwt_private_key" not in (svc.get("secrets") or [])
            assert "JWT_PRIVATE_KEY" not in str(svc.get("environment") or {})
    anchors = yaml.safe_load(compose_text)["x-backend-env"]
    assert "JWT_SECRET" not in anchors


def test_apps_get_only_public_keys(services):
    for name, svc in services.items():
        if name.endswith("-backend") and name != "center-backend":
            assert svc["environment"]["JWT_PUBLIC_KEYS_FILE"] == "/run/secrets/jwt_public_keys"
            assert svc["secrets"] == ["jwt_public_keys"]


def test_frontends_and_gateway_receive_no_environment(services):
    for name, svc in services.items():
        if name.endswith("-frontend") or name == "gateway":
            assert "environment" not in svc and "secrets" not in svc


def test_every_backend_connects_with_its_own_role(infra, services):
    seen = set()
    for app in ["center"] + [a.slug for a in infra.ALL_APPS]:
        url = services[f"{app}-backend"]["environment"]["DATABASE_URL"]
        match = re.fullmatch(
            r"postgresql\+psycopg://(\w+):\$\{(DB_PASSWORD_\w+):\?[^}]+\}@postgres:5432/(\w+)", url
        )
        assert match, url
        role, var, database = match.groups()
        assert (role, var, database) == (f"sn_{app}", f"DB_PASSWORD_{app.upper()}", app)
        seen.add(role)
    assert len(seen) == len(infra.ALL_APPS) + 1 and "postgres" not in seen


def test_superuser_password_stays_on_the_postgres_service(services):
    for name, svc in services.items():
        assert ("POSTGRES_PASSWORD" in (svc.get("environment") or {})) == (name == "postgres")


def test_postgres_receives_every_service_password(infra, services):
    env = services["postgres"]["environment"]
    for app in ["center"] + [a.slug for a in infra.ALL_APPS]:
        assert f"DB_PASSWORD_{app.upper()}" in env
    assert any("init-roles.sh" in volume for volume in services["postgres"]["volumes"])


def test_role_scripts_cover_every_service_and_lock_the_roles_down(infra):
    for script in (infra.init_roles_sh(), infra.apply_roles_sh()):
        for app in ["center"] + [a.slug for a in infra.ALL_APPS]:
            assert f"provision sn_{app} {app} DB_PASSWORD_{app.upper()}\n" in script
        assert "NOSUPERUSER NOCREATEDB NOCREATEROLE" in script
        assert "REVOKE ALL ON DATABASE %I FROM PUBLIC" in script
        assert "REVOKE CONNECT ON DATABASE %I FROM PUBLIC" in script
        assert "REASSIGN OWNED" not in script
        assert script.startswith("#!/bin/sh\n")
    assert "exec -T postgres sh <" in infra.apply_roles_sh()


def test_secrets_are_files_outside_the_repository_tree_of_keys(compose_text):
    secrets = yaml.safe_load(compose_text)["secrets"]
    assert set(secrets) == {"jwt_private_key", "jwt_public_keys"}
