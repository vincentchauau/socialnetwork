"""Regenerates docker-compose.yml, nginx.conf and postgres/{init,apply}-roles.sh from the app list.

Run from anywhere:  python shared/infra/generate_infra.py [--apps all|none|chat,face,...]
`--apps none` generates a stack with only postgres + center + the gateway (auth work); the other
apps are left out of compose, nginx and the home-page app list, so nginx still starts. Run with
`--apps all` (the default) to bring them back, then `docker compose up -d --remove-orphans`.
Add an app by appending to ALL_APPS (and creating <slug>/backend and <slug>/frontend).
An App can declare extra backend environment (`backend_env`) and extra compose services (`services`: a worker built
from the same Dockerfile, or stock images such as brokers), each optionally behind a compose profile (see `api`).
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
    """An extra compose service declared by an App (see `api`). Emitted by `render_service`.

    `image` makes it a stock image; an empty `image` builds the owning app's backend Dockerfile (the same
    image with another `command`). `profiles` keeps it off unless that compose profile is enabled.
    """

    name: str
    image: str = ""
    build: str = ""  # a folder (next to the compose file) with the Dockerfile of a service of its own
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
    extra_uploads: tuple[tuple[str, str], ...] = ()  # more (backend path, client_max_body_size) upload routes
    stream: bool = False  # serves large ranged responses: no response buffering
    tmp_mb: int = 0  # size cap for the backend's tmpfs /tmp (multipart spool)
    backend_env: tuple[tuple[str, str], ...] = ()  # extra environment for <slug>-backend
    services: tuple[Service, ...] = ()  # extra services (workers, brokers, ...), see Service
    backend_starts_after: tuple[str, ...] = ()  # extra services <slug>-backend waits for (started, not healthy)
    frontend: bool = True  # False: a backend only (its pages live in another app's frontend)
    backend: bool = True  # False: a frontend only (it talks to the backends of other apps through /api/<their slug>)
    # Public routes that reach another app's backend: (public path, backend app slug, path on that backend).
    # Exact match, no auth_request: the backend authenticates the caller itself (a signed webhook).
    public_routes: tuple[tuple[str, str, str], ...] = ()
    # The backend of this app runs inside another service (`core`): no `<slug>-backend` of its own, its database role and database
    # stay its own, and the gateway sends /api/<slug>/ to /<slug>/ of the host.
    backend_in: str = ""
    data_dir: str = ""  # the folder of /data where its files are kept, when it is not the slug
    hosts: tuple[str, ...] = ()  # the apps whose backends run in this one: each gets <SLUG>_DATABASE_URL here


_BROKERS = (
    ("RABBITMQ_HOST", "rabbitmq"),
    ("RABBITMQ_USER", "${RABBITMQ_USER:-sn}"),
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
    ("KAFKA_AUTO_CREATE_TOPICS_ENABLE", "false"),  # a module creates its topic
    ("KAFKA_LOG_RETENTION_MS", "3600000"),
    ("KAFKA_LOG_RETENTION_BYTES", "52428800"),
    ("KAFKA_LOG_SEGMENT_BYTES", "16777216"),
    ("KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS", "60000"),
    ("KAFKA_HEAP_OPTS", "-Xms256m -Xmx384m"),
)
_LIVEKIT = Service(
    "livekit",
    image="livekit/livekit-server:v1.13.11",
    environment=(
        # The whole configuration in one line (YAML): signalling on 7880, the media over TCP 7881 and UDP 7882 (both published), no TURN needed.
        ("LIVEKIT_CONFIG", "{port: 7880, log_level: info, rtc: {tcp_port: 7881, udp_port: 7882, use_external_ip: false, node_ip: 127.0.0.1}, "
                           "keys: {${LIVEKIT_API_KEY:?set LIVEKIT_API_KEY in .env}: ${LIVEKIT_API_SECRET:?set LIVEKIT_API_SECRET in .env (hex)}}}"),
    ),
    ports=("127.0.0.1:7880:7880", "7881:7881", "7882:7882/udp"),
    comment="LiveKit: the video of the calls of the rooms. The browsers reach it at ws://localhost:7880 and send the media to 7881 (TCP) and 7882 (UDP).",
)
_CALLEAR = Service(
    "callear",
    build="./callear",
    environment=(
        ("CALLEAR_SECRET", "${CALLEAR_SECRET:?set CALLEAR_SECRET in .env (hex)}"),
        ("LIVEKIT_API_KEY", "${LIVEKIT_API_KEY:-}"), ("LIVEKIT_API_SECRET", "${LIVEKIT_API_SECRET:-}"),
        ("LIVEKIT_INTERNAL_URL", "ws://livekit:7880"), ("CHAT_INTERNAL_URL", "http://api-backend:8000/chat"),
    ),
    depends_on=(("livekit", "service_started"), ("api-backend", "service_healthy")),
    comment="The ear of the calls: listens to the microphones in a call (a hidden listener of LiveKit) and hands what each person says to the chat.",
)
_MESSAGING_SERVICES = (
    Service(
        "api-worker",
        command=("python", "-m", "api.worker"),
        environment=_BROKERS,
        profiles=("messaging",),
        depends_on=(
            ("api-backend", "service_healthy"),
            ("rabbitmq", "service_healthy"),
            ("kafka", "service_healthy"),
        ),
        health=Health('test -n "$$(find /tmp/worker-alive -mmin -1 2>/dev/null)"', timeout="3s", start_period="30s"),
        comment="The worker of the backend (same image as api-backend): one consumer per queue declared in api/worker.py (touches /tmp/worker-alive).",
    ),
    Service(
        "rabbitmq",
        image="rabbitmq:4-management-alpine",
        environment=(
            ("RABBITMQ_DEFAULT_USER", "${RABBITMQ_USER:-sn}"),
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
    App("chat", "Chat", "Trò chuyện theo phòng, thời gian thực", websocket=True, needs_origin=True, backend_in="api",
        # The video calls of the rooms are held by LiveKit (the service `livekit` of the api app): the backend signs the tickets to a room with
        # the key and the secret, tells the browsers where LiveKit is (LIVEKIT_URL), and closes a room through LIVEKIT_HTTP.
        backend_env=(("LIVEKIT_URL", "${LIVEKIT_URL:-ws://localhost:7880}"), ("LIVEKIT_HTTP", "http://livekit:7880"),
            ("LIVEKIT_API_KEY", "${LIVEKIT_API_KEY:-}"), ("LIVEKIT_API_SECRET", "${LIVEKIT_API_SECRET:-}"),
            # The ear of the calls (the service `callear`): where it is, and the secret that signs the calls both ways.
            ("CALLEAR_URL", "http://callear:8200"), ("CALLEAR_SECRET", "${CALLEAR_SECRET:-}"),
            # The agent (inside the chat) writes the words of the virtual people. AI_PROVIDER=gemini in .env turns on the real Gemini
            # (key from GEMINI_API_KEY or GOOGLE_API_KEY); the default is the dummy provider, which sends nothing out.
            ("AI_PROVIDER", "${AI_PROVIDER:-dummy}"), ("GEMINI_API_KEY", "${GEMINI_API_KEY:-${GOOGLE_API_KEY:-}}"),
            # The werewolf and the chat call each other with a body signed by this secret.
            ("WEREWOLF_SECRET", "${WEREWOLF_SECRET:-}"),
            # CHAT_CLUSTER=1 lets several copies of the chat share frames and presence through Redis (see chat/backend/app/cluster.py).
            ("CHAT_CLUSTER", "${CHAT_CLUSTER:-}"))),
    # werewolf: the game (rooms live in memory; only the results are stored). The chat asks it for the game of a room with a call signed by
    # WEREWOLF_SECRET (its own secret, not the agent's), and WEREWOLF_URL says where it is: this very host.
    App("werewolf", "Werewolf", "Chơi trò Ma sói", websocket=True, backend_in="api",
        backend_env=(("WEREWOLF_URL", "http://127.0.0.1:8000/werewolf"), ("WEREWOLF_SECRET", "${WEREWOLF_SECRET:-}"), ("CHAT_URL", "http://127.0.0.1:8000/chat"), ("WEREWOLF_SNAPSHOT_KEY", "${WEREWOLF_SNAPSHOT_KEY:-}"))),
    # file: the files of the people (FILE_DATA_DIR); the upload is authenticated before the body is read, with its own size limit.
    App("file", "File", "Quản lý tệp và thư mục", backend_in="api", upload_path="/upload", max_body="21m", tmp_mb=64,
        needs_origin=True,  # ALLOWED_ORIGINS (follows PUBLIC_ORIGIN) for the Origin check of the unsafe routes
        backend_env=(("FILE_DATA_DIR", "/data/file"),)),
    # database: the home page; its tables are the records of each app (see /records in backend/api/main.py), so it has no backend of its own.
    App("database", "Database", "Cơ sở dữ liệu thử và cơ sở dữ liệu của các ứng dụng", backend=False),
    # api: the backend of every app in ONE process (see backend/api/main.py). All modules share one database (see `database_url`).
    App("api", "API", "Backend: mọi mô-đun trong một tiến trình", frontend=False,
        hosts=("center", "chat", "werewolf", "file", "face", "roulette", "job", "market"),
        backend_env=(*_BROKERS, ("RECORDS_DATA_DIR", "/data/records")), services=(*_MESSAGING_SERVICES, _LIVEKIT, _CALLEAR)),
    App("face", "Face", "Đo cân đối khuôn mặt", backend_in="api"),
    App("roulette", "Roulette", "Chơi Roulette bằng chip ảo", backend_in="api"),
    App("job", "Jobs", "Tìm việc và tuyển dụng", backend_in="api"),
    App("market", "Market", "Mua bán sản phẩm", backend_in="api"),
)

# The apps that are generated into compose/nginx/apps.ts; narrowed by --apps in main().
APPS: tuple[App, ...] = ALL_APPS

PROXY_HEADERS = """        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
"""


# The settings of the center (accounts, tokens, mail, sign-in methods) in the process that hosts it. JWT_SECRET and the private key are
# the center's; having them in the same process as the other modules is the price of one backend.
CENTER_ENV: tuple[tuple[str, str], ...] = (
    ('JWT_SECRET', '${JWT_SECRET:?set JWT_SECRET in .env (32+ characters, center only)}'),
    ('JWT_PRIVATE_KEY_FILE', '/run/secrets/jwt_private_key'),
    ('JWT_PUBLIC_KEYS_FILE', '/run/secrets/jwt_public_keys'),
    ('JWT_KEY_ID', '${JWT_KEY_ID:-}'),
    ('APP_ENV', '${APP_ENV:-development}'),
    ('ALLOWED_ORIGINS', '${PUBLIC_ORIGIN:-http://localhost:8080}'),
    ('ACCESS_TOKEN_MINUTES', '${ACCESS_TOKEN_MINUTES:-60}'),
    ('REFRESH_DAYS', '${REFRESH_DAYS:-14}'),
    ('GOOGLE_CLIENT_ID', '${GOOGLE_CLIENT_ID:-}'),
    ('BIOMETRICS_ENABLED', '${BIOMETRICS_ENABLED:-0}'),
    ('DATA_KEY', '${DATA_KEY:-}'),
    ('WEBAUTHN_RP_ID', '${WEBAUTHN_RP_ID:-}'),
    ('WEBAUTHN_RP_NAME', '${WEBAUTHN_RP_NAME:-Mạng xã hội}'),
    ('PUBLIC_URL', '${PUBLIC_ORIGIN:-http://localhost:8080}'),
    ('SMTP_HOST', '${SMTP_HOST:-mailpit}'),
    ('SMTP_PORT', '${SMTP_PORT:-1025}'),
    ('SMTP_USER', '${SMTP_USER:-}'),
    ('SMTP_PASSWORD', '${SMTP_PASSWORD:-}'),
    ('SMTP_FROM', '${SMTP_FROM:-Mạng xã hội <no-reply@localhost>}'),
    ('SMTP_STARTTLS', '${SMTP_STARTTLS:-0}'),
    ('SMTP_SSL', '${SMTP_SSL:-0}'),
    ('SMTP_ALLOW_PLAINTEXT_AUTH', '${SMTP_ALLOW_PLAINTEXT_AUTH:-0}'),
    ('SMS_PROVIDER', '${SMS_PROVIDER:-}'),
    ('SMS_DAILY_CAP', '${SMS_DAILY_CAP:-500}'),
    ('SMS_ALLOWED_PREFIXES', '${SMS_ALLOWED_PREFIXES:-}'),
    ('TWILIO_ACCOUNT_SID', '${TWILIO_ACCOUNT_SID:-}'),
    ('TWILIO_AUTH_TOKEN', '${TWILIO_AUTH_TOKEN:-}'),
    ('TWILIO_FROM', '${TWILIO_FROM:-}'),
    ('REDIS_URL', 'redis://:${REDIS_PASSWORD}@redis:6379/0'),
)


# One database for every table of every app: the tables of the modules have names of their own, so they sit side by side in `public`.
DB_NAME = "app"
DB_ROLE = "sn_app"  # the one LOGIN role: it owns the database and everything in it
DB_PASSWORD_VAR = "DB_PASSWORD_APP"


def database_url() -> str:
    """The address of the one database (every module is given the same)."""
    return f"postgresql+psycopg://{DB_ROLE}:${{{DB_PASSWORD_VAR}:?set {DB_PASSWORD_VAR} in .env (hex)}}@postgres:5432/{DB_NAME}"


def _q(value: str) -> str:
    """A YAML double-quoted scalar (compose still interpolates ${VAR} inside it)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def backend_dir(app: App) -> str:
    """Where the Dockerfile of the backend is: every app's backend runs in the one `backend/` (see App.backend_in)."""
    return "backend"


def render_service(app: App, svc: Service) -> str:
    lines = [f"  # {svc.comment}"] if svc.comment else []
    lines += [f"  {svc.name}:", "    <<: *hardening"]
    if not svc.drop_all_caps:
        lines.append("    cap_drop: []")
    if svc.build:
        lines += ["    build:", f"      context: {svc.build}"]
    elif svc.image:
        lines.append(f"    image: {svc.image}")
    else:
        lines += ["    build:", "      context: ../..", f"      dockerfile: {backend_dir(app)}/Dockerfile"]
    if svc.command:
        lines.append("    command: [" + ", ".join(_q(part) for part in svc.command) + "]")
    if svc.profiles:
        lines.append("    profiles: [" + ", ".join(_q(p) for p in svc.profiles) + "]")
    if svc.ports:
        lines += ["    ports:", *(f"      - {_q(port)}" for port in svc.ports)]
    env = [("DATABASE_URL", database_url()), *svc.environment] if svc.uses_db else list(svc.environment)
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
        hosted = [other for other in APPS if other.slug in app.hosts]  # the apps whose backends run in this service
        databases = [f"      DATABASE_URL: {database_url()}"]  # one database for every module
        wanted = [
            ("JWT_PUBLIC_KEYS_FILE", "/run/secrets/jwt_public_keys"),  # apps verify only; they never see a private key
            ("REDIS_URL", "redis://:${REDIS_PASSWORD}@redis:6379/0"),  # revocation checks (sn_shared.revocation)
        ]
        if app.needs_origin or any(other.needs_origin for other in hosted):
            wanted.append(("ALLOWED_ORIGINS", "${PUBLIC_ORIGIN:-http://localhost:8080}"))
        wanted += list(app.backend_env)
        if "center" in app.hosts:
            wanted += list(CENTER_ENV)
        for other in hosted:
            wanted += list(other.backend_env)
            if other.volume:
                wanted.append((f"{other.slug.upper()}_UPLOAD_DIR", f"/data/{other.data_dir or other.slug}"))  # the files of each stay in its own folder
        settings: dict[str, str] = {}
        for key, value in wanted:
            assert settings.setdefault(key, value) == value, f"two modules want {key} to be different"  # (the same setting twice is fine)
        env = ["      <<: *backend-env", *databases, *(f"      {key}: {_q(value)}" for key, value in settings.items())]
        with_center = "center" in app.hosts
        backend = [
            f"  {app.slug}-backend:",
            "    <<: *hardening",
            "    build:",
            "      context: ../..",
            f"      dockerfile: {backend_dir(app)}/Dockerfile",
            *(["      args:", "        WITH_BIOMETRICS: ${WITH_BIOMETRICS:-0}"] if with_center else []),
            "    environment:",
            *env,
            "    secrets:",
            *(["      - jwt_private_key"] if with_center else []),
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
        elif any(other.volume or any(value.startswith("/data") for _, value in other.backend_env) for other in hosted):  # each hosted app keeps its files in a folder of its own
            # one folder for the data of every hosted app: `backend/data` of the sources, as /data (each app keeps to a folder of its own in it)
            backend += ["    volumes:", "      - ../../backend/data:/data"]
        tmp_mb = max([app.tmp_mb, *(other.tmp_mb for other in hosted)])
        if tmp_mb:
            backend += ["    tmpfs:", f"      - /tmp:size={tmp_mb}m"]
        if app.backend and not app.backend_in:
            services.append("\n".join(backend))
        services += [render_service(app, svc) for svc in app.services]

    gateway_deps = ["      - web-frontend"]
    for app in APPS:
        if app.backend and not app.backend_in:
            gateway_deps.append(f"      - {app.slug}-backend")
    volumes = ["  pgdata:"] + [f"  {app.slug}-data:" for app in APPS if app.volume and not app.backend_in]  # (the apps hosted in the backend keep their files in backend/data)
    db_password_env = [f"      {DB_PASSWORD_VAR}: ${{{DB_PASSWORD_VAR}:?set {DB_PASSWORD_VAR} in .env (hex)}}"]

    return f"""name: socialnetwork

# GENERATED by shared/infra/generate_infra.py - edit APPS there, not this file.
# Run from the repo root:
#   docker compose --env-file .env -f shared/infra/docker-compose.yml up --build

x-hardening: &hardening
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
  restart: unless-stopped

# Shared by every backend. JWT_SECRET is deliberately NOT here: only the process that hosts the center gets it.
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

  # The pages of every app in ONE Next app (frontend): the center at the root, each other app under /<slug>.
  web-frontend:
    <<: *hardening
    build:
      context: ../..
      dockerfile: frontend/Dockerfile

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
# the files are NOT in the repository. Only the backend that hosts the center gets the private key.
secrets:
  jwt_private_key:
    file: ./secrets/jwt_private.pem
  jwt_public_keys:
    file: ./secrets/jwt_public_keys.pem

volumes:
{chr(10).join(volumes)}
"""


def upstream(app: App) -> str:
    """Where the gateway sends the calls of an app's backend: its own service, or its place in the service that hosts it."""
    if app.backend_in:
        return f"{app.backend_in}-backend:8000/{app.slug}"
    return f"{app.slug}-backend:8000"


def upload_location(app: App, path: str | None = None, max_body: str | None = None) -> str:
    """Exact-match location for an upload route: authenticate BEFORE the body is read."""
    path = path or app.upload_path
    max_body = max_body or app.max_body
    return f"""    location = /api/{app.slug}{path} {{
        auth_request /_auth;                  # 401 before any upload bytes are accepted
        client_max_body_size {max_body};
        client_body_timeout 60s;
        limit_req zone=upload burst=10 nodelay;
        limit_req_status 429;
        limit_conn upload_conn 3;
        proxy_request_buffering off;          # stream the body to the backend
        proxy_pass http://{upstream(app)}{path};
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
    lines.append(f"        proxy_pass http://{upstream(app)}/;")
    lines.append(PROXY_HEADERS.rstrip("\n"))
    lines.append("    }")
    block = "\n".join(lines)
    if app.upload_path:
        extra = [upload_location(app, path, size) for path, size in app.extra_uploads]
        return "\n\n".join([upload_location(app), *extra, block])
    return block


def public_route_location(path: str, backend_slug: str, target: str) -> str:
    """An exact public path proxied to another app's backend (a webhook the backend verifies itself)."""
    return f"""    location = {path} {{
        proxy_pass http://{upstream(next(a for a in ALL_APPS if a.slug == backend_slug))}{target};
{PROXY_HEADERS.rstrip(chr(10))}
    }}"""


MOVED_PAGES = """    # Pages that moved: the old links keep working.
    location ~ ^/chat/werewolf(/.*)?$ {
        return 301 $scheme://$http_host/werewolf$1;  # (the host as asked, with its port)
    }
    # The people of the chat were a page of their own (/social): the old links come here.
    location ~ ^/social(/.*)?$ {
        return 301 $scheme://$http_host/chat/people$1;
    }
    location ~ ^/(job)s(/.*)?$ {
        return 301 $scheme://$http_host/$1$2;
    }
    # ChatWork was split in three apps: /chatwork/file is /file, /chatwork/database is /database, the rest is /chat.
    location ~ ^/chatwork/(file|database)(/.*)?$ {
        return 301 $scheme://$http_host/$1$2;
    }
    location ~ ^/chatwork(/.*)?$ {
        return 301 $scheme://$http_host/chat$1;
    }"""


def nginx() -> str:
    api = "\n\n".join(api_location(app) for app in APPS if app.backend and not app.hosts)
    public = [public_route_location(path, slug, target) for app in APPS for path, slug, target in app.public_routes]
    api = "\n\n".join([*public, api] if public else [api])
    if any(app.slug == "werewolf" for app in APPS):  # what the chat asks of the game is inside: a browser never reaches it
        for internal in ("werewolf", "chat"):  # (the game asks the chat, and the chat asks the game, by a signed call)
            api += f"\n\n    location ^~ /api/{internal}/internal/ {{\n        return 404;\n    }}"
    frontends = MOVED_PAGES if any(app.slug == "chat" for app in APPS) else ""  # (pages that moved: old links keep working)
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
    add_header X-Frame-Options "SAMEORIGIN" always;  # the chat is shown in a frame under the page of each app
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Internal subrequest used by `auth_request`: valid cookie -> 200, otherwise 401.
    location = /_auth {{
        internal;
        proxy_pass http://api-backend:8000/center/auth/me;
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
        rewrite ^/api/center/(.*)$ /center/$1 break;
        proxy_pass http://api-backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /api/center/auth/ {{
        limit_req zone=auth burst=20 nodelay;
        limit_req_status 429;
        proxy_pass http://api-backend:8000/center/auth/;
{PROXY_HEADERS.rstrip(chr(10))}
    }}

    location /api/center/ {{
        proxy_pass http://api-backend:8000/center/;
{PROXY_HEADERS.rstrip(chr(10))}
    }}

    # --- app APIs ---
{api}

    # --- pages: one frontend serves the center at / and every app under /<slug> ---
{frontends}

    location / {{
        proxy_pass http://web-frontend:3000;
        proxy_set_header Host $host;
    }}
}}
"""


ROLES_PRELUDE = """set -eu
# One LOGIN role, owner of the one database of the apps; nobody else (PUBLIC) may connect to it.
# Its password comes from the environment of the postgres container (DB_PASSWORD_APP).
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
  # Tables and functions created earlier by the superuser (a database that already holds data) move to the role.
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
  -- the functions the apps made (not the ones an extension brought) belong to the role too: it must be able to replace them
  FOR item IN
    SELECT p.oid::regprocedure AS signature
    FROM pg_proc p
    WHERE p.pronamespace = 'public'::regnamespace
      AND pg_get_userbyid(p.proowner) <> owner
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
  LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO %I', item.signature, owner);
  END LOOP;
END
$$;
SQL
}
"""

ROLES_FINALE = """
# The maintenance databases are not a way around the database of the apps.
admin --dbname postgres <<'SQL'
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
SQL
"""


def roles_body() -> str:
    calls = f"provision {DB_ROLE} {DB_NAME} {DB_PASSWORD_VAR}"
    return f"{ROLES_PRELUDE}\n{calls}\n{ROLES_FINALE}"


def init_roles_sh() -> str:
    return (
        "#!/bin/sh\n"
        "# GENERATED by generate_infra.py. Runs once, when the postgres volume is created (docker-entrypoint-initdb.d).\n"
        "# Creates the database and its owner role. For a volume that already exists use apply-roles.sh instead.\n"
        + roles_body()
    )


def apply_roles_sh() -> str:
    return (
        "#!/bin/sh\n"
        "# GENERATED by generate_infra.py. Idempotent: creates or updates the role and its password, makes it\n"
        "# role the owner of its database (and of the tables/sequences in it), and revokes PUBLIC access. Safe to re-run.\n"
        "# Run it against the live postgres container (which must have the DB_PASSWORD_* variables, i.e. be recreated\n"
        "# with the current compose file):\n"
        "#   docker compose --env-file .env -f shared/infra/docker-compose.yml exec -T postgres sh < shared/infra/postgres/apply-roles.sh\n"
        + roles_body()
    )


# The hamburger menu: every page that has its own entry, in groups (the label of a group is `nav.<key>` in locales.json).
MENU: tuple[tuple[str, str, str, str], ...] = (
    ("account", "Users", "/center", "center"),
    ("content", "Chat", "/chat", "chat"),
    ("fun", "Werewolf", "/werewolf", "werewolf"),
    ("fun", "Face", "/face", "face"),
    ("fun", "Roulette", "/roulette", "roulette"),
    ("personal", "Market", "/market", "market"),
    ("personal", "Jobs", "/job", "job"),
    ("personal", "File", "/file", "file"),
    ("personal", "Database", "/", "database"),
)


# The Database app is the home page of the site: it has no path of its own.
HOME_SLUG_HREF = {"database": "/"}


def apps_ts() -> str:
    entries = "\n".join(
        f'  {{ name: "{app.title}", href: "{HOME_SLUG_HREF.get(app.slug, "/" + app.slug)}", description: "{app.description}" }},'
        for app in APPS
        if app.frontend
    )
    menu = chr(10).join(
        f'  {{ group: "{group}", name: "{name}", href: "{href}" }},'
        for group, name, href, slug in MENU
        if any(app.slug == slug for app in APPS) or slug == "center"
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

export interface MenuEntry {{
  group: string;
  name: string;
  href: string;
}}

/** Every page with an entry in the main menu, in order; the groups are named `nav.<group>` in the locales. Generated by shared/infra/generate_infra.py. */
export const MENU: readonly MenuEntry[] = [
{menu}
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
    hosts = {app.backend_in for app in ALL_APPS if app.slug in wanted and app.backend_in}  # an app brings the service that hosts it
    return tuple(app for app in ALL_APPS if app.slug in wanted or app.slug in hosts)


def main() -> None:
    global APPS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apps", default="all", help="all (default), none, or e.g. chat,face")
    APPS = select_apps(parser.parse_args().apps)
    (HERE / "docker-compose.yml").write_text(compose(), encoding="utf-8", newline="\n")
    (HERE / "nginx.conf").write_text(nginx(), encoding="utf-8", newline="\n")
    (HERE / "postgres" / "init-roles.sh").write_text(init_roles_sh(), encoding="utf-8", newline="\n")
    (HERE / "postgres" / "apply-roles.sh").write_text(apply_roles_sh(), encoding="utf-8", newline="\n")
    # One list for every frontend: center's home page and the shared nav bar both read it.
    (REPO / "shared" / "frontend" / "lib" / "apps.ts").write_text(apps_ts(), encoding="utf-8", newline="\n")
    print("generated compose, nginx, postgres roles scripts, apps.ts for: center +", ", ".join(app.slug for app in APPS) or "(no apps)")


if __name__ == "__main__":
    main()
