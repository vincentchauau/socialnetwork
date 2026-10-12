# socialnetwork

A multi-app platform. `center` owns identity; every other app is its own service
(FastAPI backend + Next.js frontend) behind one nginx gateway.

```
socialnetwork/
  shared/
    backend/    sn_shared: JWT + password helpers (a library, not a service)
    frontend/   api.ts (fetch client), theme.css (design tokens)
    infra/      generate_infra.py -> docker-compose.yml, nginx.conf, postgres/init.sql
  center/       accounts + shell UI (home, sign-in, app list)
  chat/         rooms + realtime messages (WebSocket)
  photos/       share photos, likes, comments (uploads on a volume)
  watch/        upload and stream videos, progress, watchlist (uploads on a volume)
  werewolf/     realtime social-deduction game (rooms in memory, results in DB)
  market/       products, cart, orders, reviews (payments are a stub)
  learning/     courses, lessons, quizzes, progress, certificates
  jobs/         postings, applications, saved jobs, candidate profile
                (each app = backend/ FastAPI + frontend/ Next.js, served at /<app>)
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
  /<app>         -> <app>-frontend   (chat, photos, watch, werewolf, market, learning, jobs)
  /api/center/*  -> center-backend   (prefix stripped)
  /api/<app>/*   -> <app>-backend    (prefix stripped; WebSocket upgrade for chat and werewolf)
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

1. Copy an existing app (`chat/` is the smallest) to `<app>/`, rename, and replace the domain code.
2. Add it to `APPS` in `shared/infra/generate_infra.py` (set `volume`, `websocket`, `max_body`... as needed).
3. Run `python shared/infra/generate_infra.py`. It rewrites `docker-compose.yml`, `nginx.conf`,
   `postgres/init.sql` and `center/frontend/app/apps.ts` (the home-page app list).
4. `init.sql` only runs on a **fresh** Postgres volume. For an existing one create the database by hand:
   `docker compose ... exec postgres psql -U postgres -c "CREATE DATABASE <app>"`.
5. Protect routes with `Depends(get_current_user)` from `sn_shared.deps`.

## Security notes

- Uploads (photos 5 MB, videos 100 MB) are verified by content, stored under random names on a
  volume, and capped by nginx per route. Payments in `market` are a stub: no card data is handled.
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
- `werewolf` keeps rooms in memory (lost on restart) and omits the old "Ma" faction; `market` has no shipping address.
- No email verification, password reset or refresh tokens.
