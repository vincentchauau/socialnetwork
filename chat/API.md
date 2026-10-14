# chat API contract

Behind the gateway: REST at `/api/chat/*` (prefix stripped), WebSockets at `/api/chat/ws/{room}` and
`/api/chat/ws-lobby`. Auth is the center JWT cookie `sn_token` on every route. WebSockets additionally
require an allowed `Origin` header (browsers send it automatically).

Room name: `^[A-Za-z0-9_-]{1,32}$`.

## REST

| Route | Auth | Response |
|---|---|---|
| `GET /health` | none | `{"status":"ok"}` |
| `GET /rooms/{room}/messages?limit=50` (1-200) | cookie, else 401 | `[{"id":int,"room":str,"username":str,"content":str,"created_at":ISO}]`, oldest first, latest `limit`. Invalid room: 422. Only real messages: system and presence frames are never in it. |
| `GET /rooms` | cookie, else 401 | `[{"room":str,"users":int,"members":[str,...]}]` rooms with >= 1 member now, sorted by users desc then room asc, at most 100. `members` are usernames only (no ids), sorted case-insensitively, capped at 30 per room; `users` stays exact, so the list is capped when `members.length < users`. |

## WebSocket `/ws/{room}`

Handshake failures (foreign/missing Origin, missing/invalid/expired cookie, invalid room) close with `1008`
without accepting. After accept, refusals close with `1013` (try again later) and a reason:
`Too many connections` (5 sockets per user over all rooms), `Room is full` (200 distinct members),
`Too many active rooms` (500 live rooms; opening a new one). Another tab of someone already in a full room is allowed.

Client -> server (text only): `{"content":"hello"}` (1-2000 chars after trim; extra fields ignored; the
username always comes from the token).

Server -> client, dispatch on `type`:

```json
{"type":"message","id":1,"room":"g","username":"alice","content":"hi","created_at":"2026-01-01T00:00:00Z"}
{"type":"error","error":"Message must be 1-2000 characters"}
{"type":"error","error":"Only text frames are supported"}
{"type":"system","event":"join","room":"g","userId":2,"username":"bob","at":"2026-01-01T00:00:00+00:00"}
{"type":"system","event":"leave","room":"g","userId":2,"username":"bob","at":"..."}
{"type":"presence","room":"g","members":[{"userId":1,"username":"alice"}],"total":1}
```

Errors keep the connection open. `message` frames go to every socket in the room (including the sender).

Presence rules:
- A user is a member while >= 1 of their sockets is in the room (several tabs count once).
- First socket of a user: everyone in the room (including that socket) gets `system/join` then `presence`.
  Later tabs of the same user get only a `presence` snapshot on their own socket; no join.
- Last socket of a user closing: the room gets `system/leave` then `presence`.
- `members` is sorted by username case-insensitively, capped at 200; `total` is the real count.
- Names are the JWT username at connect time; after a rename they stay stale until the user reconnects.
- A new socket always receives a `presence` frame among its first frames (after `join` when it is the first).

Closes: `1008` policy (rate limit 20 msgs / 10 s, token expired, bad handshake), `1009` frame over 8 KB
(8192 chars), `1013` refusals above.

## WebSocket `/ws-lobby`

Same cookie and Origin check, same 8 KB / rate / token-expiry limits (client frames are ignored), at most 2
sockets per user (3rd: accepted then closed `1013` `Too many lobby connections`).

```json
{"type":"rooms","rooms":[{"room":"g","users":2,"members":["alice","bob"]}]}
```

Sent on connect, then whenever the set of live rooms or any count changes; coalesced to at most 2 per second
(leading push immediately, changes inside the 0.5 s window collapse into one trailing push with the latest
state). Same order/cap (100) and same room shape as `GET /rooms`.

Privacy: usernames of room members are visible to every logged-in user (usernames are public handles on the
platform; the owner accepted this so the UI can filter rooms by user name). Nothing else is exposed: no user
ids, no per-socket data. Names are the JWT username at connect time (stale after a rename until reconnect).

## Ephemeral vs stored

- Stored (DB): chat messages only (`messages`; anonymised on account deletion, renamed on rename).
- Ephemeral, memory only, per process, never stored or logged: `system` frames, `presence`, room counts,
  socket counters. With several replicas each replica has its own lists (as the existing hub).
- Restart or crash drops all presence; clients reconnect and get fresh snapshots.

## Not provided

No file manager, database manager or telnyx webhook from the original ChatWork (security decision).
