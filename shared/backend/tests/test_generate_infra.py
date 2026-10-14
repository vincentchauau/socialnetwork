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


# --- extra services (lab): brokers behind the `messaging` profile ---------------------------------------


def test_lab_extra_services_are_data_driven_and_profile_gated(services):
    for name in ("lab-worker", "rabbitmq", "kafka"):
        assert services[name]["profiles"] == ["messaging"], name
    for name in ("lab-backend", "lab-frontend", "lab-user"):
        assert "profiles" not in services[name], name
    assert services["lab-user"]["command"] == ["python", "-m", "app.user_server"]
    assert services["lab-worker"]["command"] == ["python", "-m", "app.worker"]
    assert services["lab-backend"]["depends_on"]["lab-user"]["condition"] == "service_started"
    assert not any("messaging" in str(services[n].get("depends_on", "")) for n in ("lab-backend",))


def test_lab_backends_share_one_dockerfile_and_never_get_jwt_or_broker_ports(services):
    for name in ("lab-backend", "lab-user", "lab-worker"):
        assert services[name]["build"]["dockerfile"] == "lab/backend/Dockerfile"
        assert "secrets" not in services[name] or services[name]["secrets"] == ["jwt_public_keys"]
        assert "JWT_SECRET" not in (services[name].get("environment") or {})
    assert "ports" not in services["lab-user"] and "ports" not in services["kafka"]
    assert services["rabbitmq"]["ports"] == ["127.0.0.1:15672:15672"]  # management UI only, loopback; no AMQP port


def test_lab_worker_waits_for_brokers_and_uses_its_own_role(services):
    deps = services["lab-worker"]["depends_on"]
    assert {n: deps[n]["condition"] for n in ("postgres", "lab-backend", "rabbitmq", "kafka")} == {
        "postgres": "service_healthy", "lab-backend": "service_healthy",
        "rabbitmq": "service_healthy", "kafka": "service_healthy",
    }
    assert services["lab-worker"]["environment"]["DATABASE_URL"] == services["lab-backend"]["environment"]["DATABASE_URL"]


def test_lab_kafka_is_single_node_kraft_with_small_retention(services):
    env = services["kafka"]["environment"]
    assert env["KAFKA_PROCESS_ROLES"] == "broker,controller" and "ZOOKEEPER" not in str(env)
    assert env["KAFKA_AUTO_CREATE_TOPICS_ENABLE"] == "false"
    assert env["KAFKA_LOG_RETENTION_MS"] == "3600000"
    assert "-Xmx384m" in env["KAFKA_HEAP_OPTS"]
    assert env["KAFKA_ADVERTISED_LISTENERS"].startswith("PLAINTEXT://kafka:")


def test_lab_extra_services_are_hardened_and_healthchecked(services):
    for name in ("lab-user", "lab-worker", "rabbitmq", "kafka"):
        svc = services[name]
        assert svc["security_opt"] == ["no-new-privileges:true"] and svc["restart"] == "unless-stopped", name
        assert svc["healthcheck"]["test"][0] == "CMD-SHELL", name
    assert services["kafka"]["cap_drop"] == ["ALL"] and services["rabbitmq"]["cap_drop"] == []


def test_lab_broker_password_is_required_and_in_the_gateway_routes(infra, services):
    assert "?set RABBITMQ_PASSWORD" in services["rabbitmq"]["environment"]["RABBITMQ_DEFAULT_PASS"]
    assert "location /api/lab/ {" in infra.nginx() and "location ~ ^/lab(/|$) {" in infra.nginx()
    assert '"/lab"' in infra.apps_ts()


def test_work_uploads_are_authenticated_and_the_telnyx_webhook_is_not(infra, services):
    text = infra.nginx()
    for path, size in (("/files/upload", "21m"), ("/db/import", "3m")):
        block = text.split(f"location = /api/work{path} {{", 1)[1].split("\n    }", 1)[0]
        assert "auth_request /_auth;" in block and f"client_max_body_size {size};" in block
        assert f"proxy_pass http://work-backend:8000{path};" in block
    # the generic /api/work/ location (which carries the webhook) has no auth_request
    generic = text.split("location /api/work/ {", 1)[1].split("\n    }", 1)[0]
    assert "auth_request" not in generic and "proxy_pass http://work-backend:8000/;" in generic
    backend = services["work-backend"]
    assert backend["volumes"] == ["work-data:/data"] and backend["tmpfs"] == ["/tmp:size=64m"]


def test_work_telnyx_secrets_are_passed_through_with_empty_defaults(services):
    env = services["work-backend"]["environment"]
    for name in ("TELNYX_API_KEY", "TELNYX_PUBLIC_KEY", "TELNYX_GREETING"):
        assert env[name] == "${" + name + ":-}"
    assert env["ALLOWED_ORIGINS"].startswith("${PUBLIC_ORIGIN")
    others = [name for name, svc in services.items() if name != "work-backend" and "TELNYX_API_KEY" in str(svc.get("environment"))]
    assert others == []
