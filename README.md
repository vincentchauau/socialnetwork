# socialnetwork

A multi-app platform. `center` owns identity; every other app is its own service
(FastAPI backend + Next.js frontend) behind one nginx gateway.

```
socialnetwork/
  shared/
    backend/    sn_shared: JWT + password helpers (a library, not a service)
    frontend/   api.ts (fetch client), theme.css (design tokens)
    infra/      docker-compose.yml, nginx.conf, postgres/init.sql
  center/       accounts: register / login / logout / me; shell UI (home, login)
    backend/    FastAPI
    frontend/   Next.js
  chat/         rooms + realtime messages (WebSocket)
    backend/    FastAPI
    frontend/   Next.js, served under /chat
```

## Rules

1. `shared` holds libraries and infra only. **No app business logic.**
2. Apps never call each other. They trust the JWT that `center` issues (cookie `sn_token`).
3. Each service owns its database. Never read another service's tables.
4. `center` frontend is the shell (home, sign-in, app list). App frontends are mounted by the gateway under `/<app>`.

## Request flow

```
browser -> gateway :8080
  /              -> center-frontend
  /chat          -> chat-frontend
  /api/center/*  -> center-backend   (prefix stripped)
  /api/chat/*    -> chat-backend     (prefix stripped, WebSocket upgrade)
```

Everything is same-origin, so the auth cookie is `HttpOnly` and no CORS is needed.
The chat WebSocket also checks the `Origin` header (cookies ride along automatically).

## Run everything (Docker)

Verified end to end: pages, auth cookie, chat WebSocket and rate limiting all work through the gateway.

```bash
cp .env.example .env        # then set JWT_SECRET and POSTGRES_PASSWORD
docker compose --env-file .env -f shared/infra/docker-compose.yml up --build
# open http://localhost:8080
```

## Develop one service

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r center/backend/requirements-dev.txt -e shared/backend
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")

(cd shared/backend && pytest)
(cd center/backend && pytest --cov=app)
(cd chat/backend   && pytest --cov=app)

cd center/backend && uvicorn app.main:app --reload --port 8001   # SQLite by default
cd chat/backend   && uvicorn app.main:app --reload --port 8002

cd center/frontend && npm install && npm run dev
```

## Add a new app

1. Copy `chat/` to `<app>/`, rename, and replace the domain code.
2. Add `<app>-backend` / `<app>-frontend` to `shared/infra/docker-compose.yml` and a database in `postgres/init.sql`.
3. Add a `location` for it in `shared/infra/nginx.conf` (and `basePath: "/<app>"` in its `next.config.mjs`).
4. Add an entry to `center/frontend/app/apps.ts`.
5. Protect routes with `Depends(get_current_user)` from `sn_shared.deps`.

## Security notes

- Login is throttled per (address, username) and per address; register per address. nginx also
  rate-limits `/api/center/auth/`. Backends run with `--proxy-headers` so they see the real client.
- The chat socket requires a valid cookie **and** an allowed `Origin`, caps frame size (8 KB) and rate
  (20 msgs / 10 s), and closes itself when the JWT expires.
- Containers drop privileges (`no-new-privileges`; backends and frontends also `cap_drop: ALL`).

## Known limits (intentional for now)

- Throttles and chat rooms are in-memory, per process. Move to Redis before running several replicas.
- All services share one Postgres server and superuser, and one HS256 `JWT_SECRET`. Before production:
  one DB role per service, and asymmetric keys (RS256/EdDSA) so only `center` can sign.
- JWTs cannot be revoked before they expire (24 h); logout only clears the cookie.
- The gateway serves plain HTTP and has no CSP/HSTS. Terminate TLS in front of it, set `COOKIE_SECURE=1`,
  then add HSTS and a CSP (Next.js inline scripts need nonces).
- `db.py` / `utcnow` are duplicated in `center` and `chat`; fold them into `sn_shared` when a third service needs them.
- No frontend tests and no CI yet.
- No email verification, password reset or refresh tokens.
