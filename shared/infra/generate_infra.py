"""Regenerates docker-compose.yml, nginx.conf and postgres/{init,apply}-roles.sh from the app list.

Run from anywhere:  python shared/infra/generate_infra.py [--apps all|none|chat,photos,...]
`--apps none` generates a stack with only postgres + center + the gateway (auth work); the other
apps are left out of compose, nginx and the home-page app list, so nginx still starts. Run with
`--apps all` (the default) to bring them back, then `docker compose up -d --remove-orphans`.
Add an app by appending to ALL_APPS (and creating <slug>/backend and <slug>/frontend).
An App can declare extra backend environment (`backend_env`) and extra compose services (`services`: a worker built
from the same Dockerfile, or stock images such as brokers), each optionally behind a compose profile (see `lab`).
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


@dataclass(frozen=True)
class Health:
    """A container healthcheck (CMD-SHELL). Write `$` as `$$`: the text goes into compose as-is."""

    command: str
    interval: str = "15s"
    timeout: str = "5s"
    retries: int = 5
    start_period: str = "0s"


@dataclass(frozen=True)
class Service:
    """An extra compose service declared by an App (see `lab`). Emitted by `render_service`.

    `image` makes it a stock image; an empty `image` builds the owning app's backend Dockerfile (the same
    image with another `command`). `profiles` keeps it off unless that compose profile is enabled.
    """

    name: str
    image: str = ""
    command: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    uses_db: bool = False  # adds DATABASE_URL (the owning app's role) and waits for postgres
    profiles: tuple[str, ...] = ()
    ports: tuple[str, ...] = ()
    depends_on: tuple[tuple[str, str], ...] = ()  # (service, condition)
    health: Health | None = None
    drop_all_caps: bool = True  # False: keep the default capabilities (entrypoints that chown / change user)
    comment: str = ""


@dataclass(frozen=True)
class App:
    slug: str
    title: str
    description: str
    volume: bool = False  # persistent /data mount (uploads)
    websocket: bool = False
    needs_origin: bool = False  # backend checks the WebSocket Origin
    upload_path: str = ""  # backend path that receives uploads (gets auth_request + limits)
    max_body: str = ""  # client_max_body_size for the upload path
    stream: bool = False  # serves large ranged responses: no response buffering
    tmp_mb: int = 0  # size cap for the backend's tmpfs /tmp (multipart spool)
    backend_env: tuple[tuple[str, str], ...] = ()  # extra environment for <slug>-backend
    services: tuple[Service, ...] = ()  # extra services (workers, brokers, ...), see Service
    backend_starts_after: tuple[str, ...] = ()  # extra services <slug>-backend waits for (started, not healthy)


_LAB_BROKERS = (
    ("RABBITMQ_HOST", "rabbitmq"),
    ("RABBITMQ_USER", "${RABBITMQ_USER:-lab}"),
    ("RABBITMQ_PASSWORD", "${RABBITMQ_PASSWORD:?set RABBITMQ_PASSWORD in .env (hex)}"),
    ("KAFKA_BOOTSTRAP", "kafka:9092"),
)
_KAFKA_ENV = (
    ("KAFKA_NODE_ID", "1"),
    ("KAFKA_PROCESS_ROLES", "broker,controller"),
    ("KAFKA_LISTENERS", "PLAINTEXT://:9092,CONTROLLER://:9093"),
    ("KAFKA_ADVERTISED_LISTENERS", "PLAINTEXT://kafka:9092"),
    ("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER"),
    ("KAFKA_LISTENER_SECURITY_PROTOCOL_MAP", "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT"),
    ("KAFKA_CONTROLLER_QUORUM_VOTERS", "1@kafka:9093"),
    ("KAFKA_INTER_BROKER_LISTENER_NAME", "PLAINTEXT"),
    ("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1"),
    ("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1"),
    ("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1"),
    ("KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS", "0"),
    ("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "false"),  # the lab backend / worker create lab.logs
    ("KAFKA_LOG_RETENTION_MS", "3600000"),
    ("KAFKA_LOG_RETENTION_BYTES", "52428800"),
    ("KAFKA_LOG_SEGMENT_BYTES", "16777216"),
    ("KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS", "60000"),
    ("KAFKA_HEAP_OPTS", "-Xms256m -Xmx384m"),
)
_LAB_SERVICES = (
    Service(
        "lab-user",
        command=("python", "-m", "app.user_server"),
        health=Health(
            "python -c \"import socket; socket.create_connection(('127.0.0.1', 50051), 2)\"", interval="10s", timeout="3s"
        ),
        comment="gRPC user directory (fixed demo data). Internal network only: no ports, no database, no secrets.",
    ),
    Service(
        "lab-worker",
        command=("python", "-m", "app.worker"),
        environment=_LAB_BROKERS,
        uses_db=True,
        profiles=("messaging",),
        depends_on=(
            ("lab-backend", "service_healthy"),
            ("rabbitmq", "service_healthy"),
            ("kafka", "service_healthy"),
        ),
        health=Health('test -n "$$(find /tmp/worker-alive -mmin -1 2>/dev/null)"', timeout="3s", start_period="30s"),
        comment="RabbitMQ notification consumer + Kafka log writer in one process (touches /tmp/worker-alive).",
    ),
    Service(
        "rabbitmq",
        image="rabbitmq:4-management-alpine",
        environment=(
            ("RABBITMQ_DEFAULT_USER", "${RABBITMQ_USER:-lab}"),
            ("RABBITMQ_DEFAULT_PASS", "${RABBITMQ_PASSWORD:?set RABBITMQ_PASSWORD in .env (hex)}"),
        ),
        profiles=("messaging",),
        ports=("127.0.0.1:15672:15672",),  # management UI on this machine only; AMQP (5672) is not published
        health=Health("rabbitmq-diagnostics -q ping", timeout="10s", start_period="40s"),
        drop_all_caps=False,  # the entrypoint chowns /var/lib/rabbitmq and drops to the rabbitmq user
        comment="Work queue broker. Management UI: http://localhost:15672 (user RABBITMQ_USER).",
    ),
    Service(
        "kafka",
        image="apache/kafka:3.9.0",
        environment=_KAFKA_ENV,
        profiles=("messaging",),
        health=Health(
            "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 > /dev/null 2>&1",
            interval="30s",
            timeout="10s",
            start_period="60s",
        ),
        comment="Single-node KRaft broker (no ZooKeeper), PLAINTEXT on the internal network only, not published.",
    ),
)


ALL_APPS: tuple[App, ...] = (
    App("chat", "Chat", "Trò chuyện theo phòng, thời gian thực", websocket=True, needs_origin=True),
    App("photos", "Photos", "Chia sẻ và thích ảnh", volume=True, upload_path="/photos", max_body="6m", tmp_mb=128),
    App("watch", "Watch", "Đăng và xem video", volume=True, upload_path="/videos", max_body="110m", stream=True, tmp_mb=512),
    App("werewolf", "Werewolf", "Chơi trò Ma sói", websocket=True, needs_origin=True),
    App("market", "Market", "Mua và bán sản phẩm"),
    App("learning", "Learning", "Học và dạy các khóa kỹ năng"),
    App("jobs", "Jobs", "Tìm việc hoặc tuyển người"),
    App("face", "Face", "Đo cân đối khuôn mặt"),
    App(
        "lab",
        "Lab",
        "Phòng thí nghiệm microservice",
        backend_env=(("GRPC_USER_TARGET", "lab-user:50051"), *_LAB_BROKERS),
        services=_LAB_SERVICES,
        backend_starts_after=("lab-user",),
    ),
)

# The apps that are generated into compose/nginx/apps.ts; narrowed by --apps in main().
APPS: tuple[App, ...] = ALL_APPS

PROXY_HEADERS = """        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
"""


def role_name(slug: str) -> str:
    """The Postgres LOGIN role of a service (it owns the database of the same slug)."""
    return f"sn_{slug}"


def password_var(slug: str) -> str:
    return f"DB_PASSWORD_{slug.upper()}"


def database_url(slug: str) -> str:
    var = password_var(slug)
    return f"postgresql+psycopg://{role_name(slug)}:${{{var}:?set {var} in .env (hex)}}@postgres:5432/{slug}"


def _q(value: str) -> str:
    """A YAML double-quoted scalar (compose still interpolates ${VAR} inside it)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_service(app: App, svc: Service) -> str:
    lines = [f"  # {svc.comment}"] if svc.comment else []
    lines += [f"  {svc.name}:", "    <<: *hardening"]
    if not svc.drop_all_caps:
        lines.append("    cap_drop: []")
    if svc.image:
        lines.append(f"    image: {svc.image}")
    else:
        lines += ["    build:", "      context: ../..", f"      dockerfile: {app.slug}/backend/Dockerfile"]
    if svc.command:
        lines.append("    command: [" + ", ".join(_q(part) for part in svc.command) + "]")
    if svc.profiles:
        lines.append("    profiles: [" + ", ".join(_q(p) for p in svc.profiles) + "]")
    if svc.ports:
        lines += ["    ports:", *(f"      - {_q(port)}" for port in svc.ports)]
    env = [("DATABASE_URL", database_url(app.slug)), *svc.environment] if svc.uses_db else list(svc.environment)
    if env:
        lines += ["    environment:", *(f"      {key}: {_q(value)}" for key, value in env)]
    deps = [("postgres", "service_healthy")] if svc.uses_db else []
    deps += svc.depends_on
    if deps:
        lines.append("    depends_on:")
        for name, condition in deps:
            lines += [f"      {name}:", f"        condition: {condition}"]
    if svc.health:
        h = svc.health
        lines += [
            "    healthcheck:",
            f"      test: [\"CMD-SHELL\", {_q(h.command)}]",
            f"      interval: {h.interval}",
            f"      timeout: {h.timeout}",
            f"      retries: {h.retries}",
            f"      start_period: {h.start_period}",
        ]
    return "\n".join(lines)


def compose() -> str:
    services = []
    for app in APPS:
        env = ["      <<: *backend-env",
               f"      DATABASE_URL: {database_url(app.slug)}",
               "      JWT_PUBLIC_KEYS_FILE: /run/secrets/jwt_public_keys",  # apps verify only; they never see a private key
               "      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0"]  # revocation checks (sn_shared.revocation)
        if app.needs_origin:
            env.append("      ALLOWED_ORIGINS: ${PUBLIC_ORIGIN:-http://localhost:8080}")
        env += [f"      {key}: {_q(value)}" for key, value in app.backend_env]
        backend = [
            f"  {app.slug}-backend:",
            "    <<: *hardening",
            "    build:",
            "      context: ../..",
            f"      dockerfile: {app.slug}/backend/Dockerfile",
            "    environment:",
            *env,
            "    secrets:",
            "      - jwt_public_keys",
            "    depends_on:",
            "      postgres:",
            "        condition: service_healthy",
            "      redis:",
            "        condition: service_healthy",
        ]
        for name in app.backend_starts_after:
            backend += [f"      {name}:", "        condition: service_started"]
        if app.volume:
            backend += ["    volumes:", f"      - {app.slug}-data:/data"]
        if app.tmp_mb:
            backend += ["    tmpfs:", f"      - /tmp:size={app.tmp_mb}m"]
        frontend = [
            f"  {app.slug}-frontend:",
            "    <<: *hardening",
            "    build:",
            "      context: ../..",
            f"      dockerfile: {app.slug}/frontend/Dockerfile",
        ]
        services.append("\n".join(backend))
        services.append("\n".join(frontend))
        services += [render_service(app, svc) for svc in app.services]

    gateway_deps = ["      - center-backend", "      - center-frontend"]
    for app in APPS:
        gateway_deps += [f"      - {app.slug}-backend", f"      - {app.slug}-frontend"]
    volumes = ["  pgdata:"] + [f"  {app.slug}-data:" for app in APPS if app.volume]
    db_password_env = [
        f"      {password_var(slug)}: ${{{password_var(slug)}:?set {password_var(slug)} in .env (hex)}}"
        for slug in ["center"] + [app.slug for app in APPS]
    ]

    return f"""name: socialnetwork

# GENERATED by shared/infra/generate_infra.py - edit APPS there, not this file.
# Run from the repo root:
#   docker compose --env-file .env -f shared/infra/docker-compose.yml up --build

x-hardening: &hardening
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
  restart: unless-stopped

# Shared by every backend. JWT_SECRET is deliberately NOT here: it stays on center-backend alone.
x-backend-env: &backend-env
  APP_ENV: ${{APP_ENV:-development}}
  COOKIE_SECURE: ${{COOKIE_SECURE:-0}}

services:
  postgres:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      # The superuser password lives on this service only; each service connects as its own role.
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}}
{chr(10).join(db_password_env)}
    volumes:
      - pgdata:/var/lib/postgresql/data
      # Runs on a FRESH volume only; on an existing one use postgres/apply-roles.sh (see README).
      - ./postgres/init-roles.sh:/docker-entrypoint-initdb.d/init-roles.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 10

  # Shared throttle counters and single-use challenge markers (center REDIS_URL). Internal network only,
  # nothing persisted: every key has a TTL; noeviction (writes fail rather than dropping a revocation) so monitor memory.
  redis:
    image: redis:7-alpine
    user: redis  # already unprivileged: the entrypoint then skips its setuid step, which cap_drop ALL forbids
    <<: *hardening
    command:
      - redis-server
      - --requirepass
      - ${{REDIS_PASSWORD:?set REDIS_PASSWORD in .env}}
      - --save
      - ""
      - --appendonly
      - "no"
      - --maxmemory
      - 128mb
      - --maxmemory-policy
      - noeviction
    environment:
      REDIS_PASSWORD: ${{REDIS_PASSWORD}}
    healthcheck:
      test: ['CMD-SHELL', 'redis-cli --no-auth-warning -a "$$REDIS_PASSWORD" ping | grep -q PONG']
      interval: 5s
      timeout: 3s
      retries: 10

  center-backend:
    <<: *hardening
    build:
      context: ../..
      dockerfile: center/backend/Dockerfile
      args:
        WITH_BIOMETRICS: ${{WITH_BIOMETRICS:-0}}
    environment:
      <<: *backend-env
      DATABASE_URL: {database_url("center")}
      JWT_SECRET: ${{JWT_SECRET:?set JWT_SECRET in .env (32+ characters, center only)}}
      JWT_PRIVATE_KEY_FILE: /run/secrets/jwt_private_key
      JWT_PUBLIC_KEYS_FILE: /run/secrets/jwt_public_keys
      JWT_KEY_ID: ${{JWT_KEY_ID:-}}
      APP_ENV: ${{APP_ENV:-development}}
      ALLOWED_ORIGINS: ${{PUBLIC_ORIGIN:-http://localhost:8080}}
      ACCESS_TOKEN_MINUTES: ${{ACCESS_TOKEN_MINUTES:-60}}
      REFRESH_DAYS: ${{REFRESH_DAYS:-14}}
      GOOGLE_CLIENT_ID: ${{GOOGLE_CLIENT_ID:-}}
      BIOMETRICS_ENABLED: ${{BIOMETRICS_ENABLED:-0}}
      DATA_KEY: ${{DATA_KEY:-}}
      WEBAUTHN_RP_ID: ${{WEBAUTHN_RP_ID:-}}
      WEBAUTHN_RP_NAME: ${{WEBAUTHN_RP_NAME:-Mạng xã hội}}
      PUBLIC_URL: ${{PUBLIC_ORIGIN:-http://localhost:8080}}
      SMTP_HOST: ${{SMTP_HOST:-mailpit}}
      SMTP_PORT: ${{SMTP_PORT:-1025}}
      SMTP_USER: ${{SMTP_USER:-}}
      SMTP_PASSWORD: ${{SMTP_PASSWORD:-}}
      SMTP_FROM: ${{SMTP_FROM:-Mạng xã hội <no-reply@localhost>}}
      SMTP_STARTTLS: ${{SMTP_STARTTLS:-0}}
      SMTP_SSL: ${{SMTP_SSL:-0}}
      SMTP_ALLOW_PLAINTEXT_AUTH: ${{SMTP_ALLOW_PLAINTEXT_AUTH:-0}}
      SMS_PROVIDER: ${{SMS_PROVIDER:-}}
      SMS_DAILY_CAP: ${{SMS_DAILY_CAP:-500}}
      SMS_ALLOWED_PREFIXES: ${{SMS_ALLOWED_PREFIXES:-}}
      TWILIO_ACCOUNT_SID: ${{TWILIO_ACCOUNT_SID:-}}
      TWILIO_AUTH_TOKEN: ${{TWILIO_AUTH_TOKEN:-}}
      TWILIO_FROM: ${{TWILIO_FROM:-}}
      REDIS_URL: redis://:${{REDIS_PASSWORD}}@redis:6379/0
    secrets:
      - jwt_private_key
      - jwt_public_keys
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  center-frontend:
    <<: *hardening
    build:
      context: ../..
      dockerfile: center/frontend/Dockerfile

{chr(10).join(s + chr(10) for s in services)}
  # Development mail sink: catches every email the app sends (nothing leaves this machine).
  # Enabled by COMPOSE_PROFILES=mail-dev in .env; in production point SMTP_* at a real server instead.
  # Web inbox: http://localhost:8025 (bound to this machine only).
  mailpit:
    image: axllent/mailpit:latest
    profiles: ["mail-dev"]
    restart: unless-stopped
    ports:
      - "127.0.0.1:8025:8025"
    environment:
      MP_SMTP_AUTH_ACCEPT_ANY: "1"
      MP_SMTP_AUTH_ALLOW_INSECURE: "1"
      MP_MAX_MESSAGES: "500"

  gateway:
    <<: *hardening
    # nginx needs CHOWN/SETUID/SETGID/NET_BIND_SERVICE at start-up; keep its
    # default capabilities instead of guessing the minimal set untested.
    cap_drop: []
    image: nginx:1.27-alpine
    ports:
      - "${{GATEWAY_PORT:-8080}}:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
{chr(10).join(gateway_deps)}

# Access-token keys (Ed25519). Create with `python -m app.cli gen-jwt-key` in center/backend (see README);
# the files are NOT in the repository. Only center-backend gets the private key.
secrets:
  jwt_private_key:
    file: ./secrets/jwt_private.pem
  jwt_public_keys:
    file: ./secrets/jwt_public_keys.pem

volumes:
{chr(10).join(volumes)}
"""


def upload_location(app: App) -> str:
    """Exact-match location for the upload route: authenticate BEFORE the body is read."""
    return f"""    location = /api/{app.slug}{app.upload_path} {{
        auth_request /_auth;                  # 401 before any upload bytes are accepted
        client_max_body_size {app.max_body};
        client_body_timeout 60s;
        limit_req zone=upload burst=10 nodelay;
        limit_req_status 429;
        limit_conn upload_conn 3;
        proxy_request_buffering off;          # stream the body to the backend
        proxy_pass http://{app.slug}-backend:8000{app.upload_path};
{PROXY_HEADERS.rstrip(chr(10))}
    }}"""


def api_location(app: App) -> str:
    lines = [f"    location /api/{app.slug}/ {{"]
    if app.stream:
        lines.append("        proxy_buffering off;  # stream video ranges back to the client")
    if app.websocket:
        lines += [
            "        proxy_http_version 1.1;",
            "        proxy_set_header Upgrade $http_upgrade;",
            "        proxy_set_header Connection $connection_upgrade;",
            "        proxy_read_timeout 1h;",
        ]
    lines.append(f"        proxy_pass http://{app.slug}-backend:8000/;")
    lines.append(PROXY_HEADERS.rstrip("\n"))
    lines.append("    }")
    block = "\n".join(lines)
    if app.upload_path:
        return upload_location(app) + "\n\n" + block
    return block


def frontend_location(app: App) -> str:
    return f"""    location ~ ^/{app.slug}(/|$) {{
        proxy_pass http://{app.slug}-frontend:3000;
        proxy_set_header Host $host;
    }}"""


def nginx() -> str:
    api = "\n\n".join(api_location(app) for app in APPS)
    frontends = "\n\n".join(frontend_location(app) for app in APPS)
    return f"""# GENERATED by shared/infra/generate_infra.py - edit APPS there, not this file.
# Single public entry point. Everything is same-origin, so the auth cookie is
# HttpOnly and no CORS is needed.

map $http_upgrade $connection_upgrade {{
    default upgrade;
    ''      close;
}}

# Brute-force guard for credential endpoints (the backends also throttle).
map $request_method $auth_key {{
    POST    $binary_remote_addr;
    default "";
}}
limit_req_zone $auth_key zone=auth:10m rate=30r/m;
# Upload routes: few requests and few parallel connections per address. Only POSTs are
# counted (an empty key is not limited), so browsing the same path stays unthrottled.
map $request_method $upload_key {{
    POST    $binary_remote_addr;
    default "";
}}
limit_req_zone $upload_key zone=upload:10m rate=60r/m;
limit_conn_zone $upload_key zone=upload_conn:10m;
# Everything else: a generous per-address ceiling against floods and expensive searches.
limit_req_zone $binary_remote_addr zone=api:10m rate=50r/s;

server {{
    listen 80;
    server_name _;
    server_tokens off;
    client_max_body_size 1m;
    limit_req zone=api burst=100 nodelay;
    limit_req_status 429;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Internal subrequest used by `auth_request`: valid cookie -> 200, otherwise 401.
    location = /_auth {{
        internal;
        proxy_pass http://center-backend:8000/auth/me;
        client_max_body_size 0;               # the subrequest carries no body; do not 413 the upload
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Host $host;
    }}

    # --- center: the prefix is stripped before reaching the service ---
    # Biometric sign-in / enrolment carry webcam recordings (up to 15 MB), so they get a larger
    # body limit than the rest of the API. Same POST-only rate limit as credential endpoints.
    location ~ ^/api/center/auth/(login/(biometric|voice|webcam)|register/(voice|webcam|combined)|me/(voice|webcam))$ {{
        client_max_body_size 16m;
        client_body_timeout 60s;
        limit_req zone=auth burst=20 nodelay;
        limit_req_status 429;
        limit_conn upload_conn 3;
        rewrite ^/api/center/(.*)$ /$1 break;
        proxy_pass http://center-backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /api/center/auth/ {{
        limit_req zone=auth burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://center-backend:8000/auth/;
{PROXY_HEADERS.rstrip(chr(10))}
    }}

    location /api/center/ {{
        proxy_pass http://center-backend:8000/;
{PROXY_HEADERS.rstrip(chr(10))}
    }}

    # --- app APIs ---
{api}

    # --- app frontends (each served under /<slug>) ---
{frontends}

    # --- shell (center frontend) ---
    location / {{
        proxy_pass http://center-frontend:3000;
        proxy_set_header Host $host;
    }}
}}
"""


ROLES_PRELUDE = """set -eu
# One LOGIN role per service, owner of its own database; nobody else (PUBLIC) may connect to it.
# Passwords come from the environment of the postgres container (DB_PASSWORD_<SERVICE>).
: "${POSTGRES_USER:=postgres}"

admin() {
  psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --username "$POSTGRES_USER" "$@"
}

# provision <role> <database> <password-env-var-name>
provision() {
  role="$1"; db="$2"; var="$3"
  eval "password=\\"\\${$var:-}\\""
  if [ -z "$password" ]; then
    echo "roles: $var is not set in the postgres container" >&2
    exit 1
  fi
  SN_ROLE_PASSWORD="$password" admin --dbname postgres -v role="$role" -v db="$db" <<'SQL'
\\getenv pw SN_ROLE_PASSWORD
SELECT format('CREATE ROLE %I', :'role') WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'role') \\gexec
SELECT format('ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L', :'role', :'pw') \\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'role') WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'db', :'role') \\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \\gexec
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'db') \\gexec
SQL
  # Tables created earlier by the superuser (a database that already holds data) move to the service role.
  admin --dbname "$db" -v role="$role" <<'SQL'
SELECT set_config('sn.owner', :'role', false);
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'role') \\gexec
DO $$
DECLARE
  owner text := current_setting('sn.owner');
  item record;
BEGIN
  FOR item IN
    SELECT c.relkind, n.nspname, c.relname
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
      AND pg_get_userbyid(c.relowner) <> owner
      AND (c.relkind <> 'S' OR NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype IN ('a', 'i')))
    ORDER BY (c.relkind = 'S'), c.relname
  LOOP
    EXECUTE format(
      'ALTER %s %I.%I OWNER TO %I',
      CASE item.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'S' THEN 'SEQUENCE' ELSE 'TABLE' END,
      item.nspname, item.relname, owner
    );
  END LOOP;
END
$$;
SQL
}
"""

ROLES_FINALE = """
# The maintenance databases are not a way around the per-service databases.
admin --dbname postgres <<'SQL'
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
SQL
"""


def roles_body() -> str:
    calls = "\n".join(
        f"provision {role_name(slug)} {slug} {password_var(slug)}" for slug in ["center"] + [app.slug for app in APPS]
    )
    return f"{ROLES_PRELUDE}\n{calls}\n{ROLES_FINALE}"


def init_roles_sh() -> str:
    return (
        "#!/bin/sh\n"
        "# GENERATED by generate_infra.py. Runs once, when the postgres volume is created (docker-entrypoint-initdb.d).\n"
        "# Creates every database and its owner role. For a volume that already exists use apply-roles.sh instead.\n"
        + roles_body()
    )


def apply_roles_sh() -> str:
    return (
        "#!/bin/sh\n"
        "# GENERATED by generate_infra.py. Idempotent: creates or updates the per-service roles and passwords, makes each\n"
        "# role the owner of its database (and of the tables/sequences in it), and revokes PUBLIC access. Safe to re-run.\n"
        "# Run it against the live postgres container (which must have the DB_PASSWORD_* variables, i.e. be recreated\n"
        "# with the current compose file):\n"
        "#   docker compose --env-file .env -f shared/infra/docker-compose.yml exec -T postgres sh < shared/infra/postgres/apply-roles.sh\n"
        + roles_body()
    )


def apps_ts() -> str:
    entries = "\n".join(
        f'  {{ name: "{app.title}", href: "/{app.slug}", description: "{app.description}" }},'
        for app in APPS
    )
    return f"""export interface AppLink {{
  name: string;
  href: string;
  description: string;
}}

/** Every app mounted behind the gateway. Generated by shared/infra/generate_infra.py. */
export const APPS: readonly AppLink[] = [
{entries}
];
"""


def select_apps(spec: str) -> tuple[App, ...]:
    """'all', 'none' or a comma-separated list of slugs (unknown slugs are an error)."""
    spec = spec.strip().lower()
    if spec == "all":
        return ALL_APPS
    if spec == "none":
        return ()
    wanted = [slug.strip() for slug in spec.split(",") if slug.strip()]
    known = {app.slug for app in ALL_APPS}
    unknown = [slug for slug in wanted if slug not in known]
    if unknown:
        raise SystemExit(f"unknown app(s): {', '.join(unknown)}; known: {', '.join(sorted(known))}")
    return tuple(app for app in ALL_APPS if app.slug in wanted)


def main() -> None:
    global APPS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apps", default="all", help="all (default), none, or e.g. chat,photos")
    APPS = select_apps(parser.parse_args().apps)
    (HERE / "docker-compose.yml").write_text(compose(), encoding="utf-8", newline="\n")
    (HERE / "nginx.conf").write_text(nginx(), encoding="utf-8", newline="\n")
    (HERE / "postgres" / "init-roles.sh").write_text(init_roles_sh(), encoding="utf-8", newline="\n")
    (HERE / "postgres" / "apply-roles.sh").write_text(apply_roles_sh(), encoding="utf-8", newline="\n")
    (REPO / "center" / "frontend" / "app" / "apps.ts").write_text(apps_ts(), encoding="utf-8", newline="\n")
    print("generated compose, nginx, postgres roles scripts, apps.ts for: center +", ", ".join(app.slug for app in APPS) or "(no apps)")


if __name__ == "__main__":
    main()
