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

## Sign-in methods (center)

One `users` row per account; six methods, **each usable on its own**, plus an optional TOTP second step, all linked to that row:

| Method | Stored in `users` | Notes |
|---|---|---|
| Password | `password_hash` (scrypt; `!` = none) | policy: 8-128 chars, not common, not the username |
| Google | `google_sub`, `email` | ID token verified server side; needs `GOOGLE_CLIENT_ID` |
| Voice | `audio_embedding` (Fernet), `voice_login` | one short audio clip; strict threshold; no username needed |
| Webcam | `face_embedding` (Fernet), `webcam_login` | one camera-only clip (no microphone); FACE ONLY; no username needed |
| **Passkey** | table `passkeys` (one row per device: `credential_id`, `public_key`, `sign_count`, `user_handle`, ...) | WebAuthn: fingerprint / Face ID / Windows Hello / security key, handled by the device; no username; **recommended over webcam/voice** |
| **Email** | `email`, `email_verified`, `email_from_google`; table `email_tokens` (hashed token + code MAC) | magic link or 6-digit code to a VERIFIED address; also verification, password reset, security notices |

- **Register** with any one or several methods at once (`POST /auth/register/combined`, all-or-nothing),
  then link the rest in `/account`. Linking/removing needs the password again when the account has one,
  and at least one method must always remain (409 otherwise).
- **Voice and webcam need no username** (like Face ID): `POST /auth/login/voice` and `/auth/login/webcam`
  without `username` identify the account themselves (1-N, `app/identify.py`). The best match must pass the
  strict threshold (face distance <= `FACE_THRESHOLD_ALONE` 0.45; voice cosine >= `AUDIO_THRESHOLD_ALONE` 0.88)
  AND beat the runner-up by a margin (`FACE_IDENTIFY_MARGIN` 0.08, `VOICE_IDENTIFY_MARGIN` 0.05), otherwise the
  attempt is rejected as ambiguous. Every failure is the same 401 and does the same work; throttled per IP
  (5 / 15 min) and globally (100 / 15 min), with separate counters for face and voice. Cost is O(N) per attempt,
  so above 5000 accounts of a method the username is required again (422 `Enter your username`).
  A face or voice already registered by another account is refused at registration (409), which also
  reveals that it is registered. Giving a username still works (1-1 check).
- The username is required at registration only when a password is chosen. Otherwise a generated one
  (`user-xxxxxx`, or derived from the Google email) is used; it can be renamed later (see Account events and rename).
- Measured with the real models: face, same person on two different photos 0.357 vs 0.844 for different people
  (threshold 0.45); voice, same synthetic speaker on two sentences 0.892 vs 0.494 for another speaker
  (threshold 0.88: **tight**, tune it on real microphone data); about 3 s per clip.
- Lesson kept in the tests: the real engine must never raise on malformed or placeholder templates (a
  placeholder of the wrong length once made username-less sign-in a 500 when no account existed).
- Voice and webcam are only available when `BIOMETRICS_ENABLED=1` (image built with `WITH_BIOMETRICS=1`,
  `DATA_KEY` set). They have **no liveness check**: anyone with a recording of the owner can pass.
- **Passkeys** (`py_webauthn` on the server, `@simplewebauthn/browser` in the UI): the server stores only the public
  key; the device verifies the user (biometrics or PIN) and signs a challenge, so there is nothing to spoof with a
  photo or a recording and no username to type (discoverable credentials). A user can have several (one per
  device). Rules: user verification required, challenges are signed, expire in 5 min and are single use
  (per process, like the throttles), a non-increasing sign counter is rejected as a possible clone, the same
  device cannot register twice for one account. `WEBAUTHN_RP_ID` (default: host of `PUBLIC_ORIGIN`) is part of
  every passkey: **changing it later invalidates all registered passkeys**. Production requires it explicitly.
- **Email** (`app/routes_email.py`, `emailtokens.py`, `mailer.py`): an address is usable for sign-in / reset only after it
  is verified (link or code). Links look like `PUBLIC_URL/login/magic#token=...`: the secret is in the URL
  **fragment**, never sent to a server or a Referer, cleared from the address bar, and consumed only by a POST after
  the user presses a button (mail scanners that prefetch links cannot burn it). Tokens are stored as SHA-256, codes
  as an HMAC; 3 live tokens per (user, purpose); 5 wrong codes kill the code (not the link); TTL verify 24 h,
  sign-in 15 min, reset 30 min. Requests always answer 202 and take the same time for known and unknown addresses
  (jitter 0-30 ms); budgets per IP 5, per (IP, address) 3, per address 10 per 15 min; wrong-code counter 10/hour per
  address. Reset kills every session (`token_version`). Links are built from `PUBLIC_URL`, never the Host header.
  A Google-supplied address is cleared on unlink only when Google wrote it (`email_from_google`).
  Development: `COMPOSE_PROFILES=mail-dev` starts **Mailpit** (inbox http://localhost:8025, API `/api/v1/messages`).
  Production: set `SMTP_HOST/PORT/USER/PASSWORD/FROM`, `SMTP_STARTTLS=1` (587) or `SMTP_SSL=1` (465);
  credentials over plain SMTP to a non-local host are refused unless `SMTP_ALLOW_PLAINTEXT_AUTH=1`.
- **TOTP + recovery codes** (`app/totp.py`, `routes_totp.py`, `pyotp`): optional second step, never a sign-in method by itself
  (it does not count toward "keep at least one method"). Off by default; turn it on in `/account` (QR drawn in the browser,
  the secret never leaves the gateway), confirm with a first code, then save the 10 recovery codes shown once (stored only as
  keyed HMACs, single use, 50 bits each). After password / Google / email / **voice / webcam** the account gets an `mfa_required`
  answer (`factors: ["totp"]`) and `POST /auth/login/totp` finishes the sign-in with a code or a recovery code. Passkeys stay a
  full factor on their own (user verification is required). With TOTP on, biometrics can NOT stand in for it. Each time step is
  accepted once (atomic `totp_last_step`), a recovery code once (atomic UPDATE); failures are one generic 401, throttled per
  IP (20) and per account (10) per 15 min. Enabling and disabling bump `token_version` (other sessions die) and mail a notice to a
  verified address. Secrets are Fernet-encrypted with `DATA_KEY` (or a key derived from `JWT_SECRET` when it is empty):
  **rotating either key makes every TOTP secret and recovery code unusable**: keep `DATA_KEY` set and stable.
  Known limits: the second-step lockout can be used to annoy an owner whose password is known;
  accounts without a verified email get no notices. At most 10 passkeys per account (409).
- **Sessions, revocation, step-up (Phase 5B)**:
  - Every sign-in creates a row in `user_sessions` (`sid`, ip, user agent, `method` = primary factor, `last_seen_at` touched at most once a minute, `revoked_at`). The `sid` is a claim of the access AND refresh token (a refresh keeps it). `GET /auth/sessions`, `DELETE /auth/sessions/{sid}` (204; own sessions only, else 404), `POST /auth/sessions/revoke-others` -> `{revoked: n}`. Logout, password change/reset and TOTP changes bump `token_version` and revoke the rows (logout ends every session; password/TOTP changes keep the current one). Rows idle longer than `REFRESH_DAYS` are purged on sign-in.
  - **Upgrade (one-time forced re-login)**: the first start that creates `user_sessions` on an existing database bumps every `token_version` once, so every pre-sessions token (which has no `sid` and could not be revoked) dies. `/auth/refresh` rejects tokens without a `sid` (generic 401). At most 50 live sessions per account (the oldest are revoked beyond that); revoked rows are purged after a day.
  - **Immediate revocation in other apps**: with `REDIS_URL`, center publishes `sn:revoked:sid:<sid>` and `sn:minver:<user_id>` (TTL = access lifetime + 60 s) and `sn_shared.deps.get_current_user` rejects such tokens (a failed publish is logged as a warning with a count; Redis runs with `noeviction` and 128 MB, every key has a TTL, **monitor its memory**: when full, writes fail and revocations are not published; needs the `redis` package; without it or without a URL the check is a no-op). **Trade-off: fail open.** If Redis errors (0.3 s timeout) the token is accepted and one line a minute is logged, so a revocation can be up to one access token lifetime (60 min) late in the OTHER apps; center always checks its database. Websocket handlers using `payload_from_cookies` get the same check.
  - **Account events and rename** (`center/app/events.py`, `shared/backend/sn_shared/events.py`): apps have their own databases and never call each other, so account changes travel as events. Center writes an outbox row in `account_events` in the SAME transaction as the change (account deletion, rename; a rolled back change leaves no event). A relay (thread started in the app lifespan, every 2 s, and once right after the commit) copies unpublished rows in id order to the Redis Stream `sn:events:account` (`XADD MAXLEN ~10000`) and sets `published_at`; published rows are purged after 7 days. Without `REDIS_URL` the relay is a no-op and rows simply stay in the table (published later when Redis is configured). Failures log one warning a minute and are retried. **Guarantee: at least once, in order per relay**: a crash between XADD and the `published_at` update re-publishes that row. Stream fields: `event_id`, `type`, `user_id`, `payload` (JSON text): `user.deleted` payload `{"old_username": "alice"}`, `user.renamed` payload `{"username": "bobby", "old_username": "alice", "seq": 42}` (`seq` = the outbox row id, monotonic). Consumers keep a per-user high-water mark in Redis (`sn:events:rename-seq:<app>:<user_id>`, 30 days) and skip a rename whose `seq` is not newer, so a late redelivery cannot overwrite a newer name; events without `seq` are always handled. Account deletion also bumps `token_version` and publishes the minimum version, so the deleted user's tokens die at once in every app, and the old username stays reserved for 30 days.
  - **Consuming**: each app calls `sn_shared.events.start_account_consumer("<app>", SessionLocal)` in its lifespan (and `.stop()` on shutdown). It runs a daemon thread with consumer group `<app>` (created at id 0, so a newly added app catches up on the retained history), `XREADGROUP`, and `XAUTOCLAIM` of entries idle for more than 60 s. For each message it calls `on_user_deleted(db, user_id)` or `on_user_renamed(db, user_id, new_username)` from the app module **`app/account_events.py`** with a fresh session and commits, then `XACK`s. **Handlers MUST be idempotent** (delivery is at least once; an event may arrive twice, late, or for a user the app never saw). An exception rolls back and leaves the message pending (retried after 60 s idle); after 5 deliveries it moves to the dead-letter stream `sn:events:account:dead` (original fields + `app`, `error` = exception class name, `original_id`, kept at ~10000) and is acknowledged. A missing module or handler is logged and acknowledged, so the stream never stalls. No `REDIS_URL`: nothing runs. Redis here is not persisted: after a Redis data loss the retained history is gone (rows already marked published are not re-sent).
  - **Rename** `POST /auth/me/username {username, password?}` (CSRF, Origin, step-up like other sensitive changes, same username rules as registration): once per 30 days per account (`users.username_changed_at`), the old name is reserved for its owner for 30 days (`reserved_usernames`; the owner may switch back), 409 `Username already taken` for a taken or reserved name (same message as registration, case-insensitive), 409 `Username can be changed again after YYYY-MM-DD` inside the 30 days, 422 for the same or an invalid name, 429 after 10 attempts a day. Concurrent renames serialise (row lock on PostgreSQL plus a conditional UPDATE), so only one wins. System names (`admin`, `root`, `support`, `center`, the app names, ...; `usernames.SYSTEM_NAMES`) are refused at register, rename and Google handle generation (another handle is chosen) with the same generic 409. **SQLite is for development only**; the users table uses `AUTOINCREMENT` there so ids are never reused (PostgreSQL sequences never reuse). It bumps `token_version` (other sessions end, revocation is published), re-issues the current session (the JWT `username` claim is the new name) and returns the Session body with a new `csrf_token`. A security mail with the old and new name goes to the verified address. `GET /auth/me` also returns `username_changed_at` and `can_rename_after` (null when a rename is allowed now). Apps keep copies of the username (e.g. chat messages): they may update them from `user.renamed`, tokens carry the new name at once.
  - **Step-up**: sensitive actions (method link/removal, email change/removal, TOTP setup/enable/disable/regenerate, account deletion) accept the password or a fresh proof (cookie `sn_fresh`, 5 min, bound to user + session). Accounts WITHOUT a password need the proof: otherwise `401 {"detail":"Re-authentication required","reauth":["passkey","google","email"]}`. Obtain it with `POST /auth/reauth/passkey/options|verify` (a passkey of the current user), `/auth/reauth/google {id_token}`, `/auth/reauth/email/request` + `/email/verify {code}` (6-digit code to the VERIFIED email, 10 min); `GET /auth/reauth/methods`. Failures are one generic 401, throttled per user. A Google ID token buys one proof only. Known limit: accounts with only voice/webcam have no step-up method and are not asked. New env: none beyond `REDIS_URL`.
- Optional advanced setting `biometric_2fa` (off by default): after password/Google, also require a sample.
- Sessions: `sn_token` (60 min) + `sn_refresh` (14 d), CSRF header on writes, `token_version` revocation.

## Security notes

- Uploads (photos 5 MB, videos 100 MB) are authenticated by nginx (`auth_request`) BEFORE the body is
  accepted, rate-limited per address (POST only), verified by content, stored under random names on a
  volume, and limited per user (photos 500; videos 20 and 1 GB). `/tmp` of those backends is a capped tmpfs.
- Quiz answers are only revealed after a passing attempt (5 attempts per day); certificates need a passed quiz.
- `market`: pending orders expire after 15 min and restock; only the buyer confirms delivery; paid
  cancellations refund through the payment provider. Payments are a stub: no card data is handled.
- Login is throttled per (address, username) and per address; register per address. nginx also
  rate-limits `/api/center/auth/`. Backends run with `--proxy-headers` so they see the real client.
- The chat socket requires a valid cookie **and** an allowed `Origin`, caps frame size (8 KB) and rate
  (20 msgs / 10 s), and closes itself when the JWT expires.
- Containers drop privileges (`no-new-privileges`; backends and frontends also `cap_drop: ALL`).

## Known limits (intentional for now)

- Chat rooms (and `werewolf` rooms) are in-memory, per process: the chat service cannot run several replicas yet.
- `center` throttles, email budgets and passkey single-use challenges live in Redis when `REDIS_URL` is set
  (compose sets it from `REDIS_PASSWORD`; keys are `sn:*`, all with a TTL, nothing is persisted). Without
  `REDIS_URL` (dev, tests) they are per process. If Redis fails at runtime, each call falls back to the
  in-process counters (limits stay on but per replica; a challenge token could be replayed once per replica
  within its 5 minutes), an ERROR is logged at most once a minute, and `/health` reports `redis: degraded`
  (`ok` when healthy, `off` when unset). The app starts even if Redis is down at boot.
- All services share one Postgres server and superuser, and one HS256 `JWT_SECRET`. Before production:
  one DB role per service, and asymmetric keys (RS256/EdDSA) so only `center` can sign.
- Other apps revoke a token immediately only when Redis is configured and reachable (fail open, see Sessions); otherwise it lives until it expires (60 min).
- The gateway serves plain HTTP and has no CSP/HSTS. Terminate TLS in front of it, set `COOKIE_SECURE=1`,
  then add HSTS and a CSP (Next.js inline scripts need nonces).
- `db.py` / `utcnow` are duplicated in `center` and `chat`; fold them into `sn_shared` when a third service needs them.
- No frontend tests and no CI yet.
- The watch per-user byte quota is not atomic under concurrent uploads (can overshoot briefly).
- A multi-seller `market` order has one shared status (any involved seller can mark it shipped).
- `werewolf` keeps rooms in memory (lost on restart) and omits the old "Ma" faction; `market` has no shipping address.
