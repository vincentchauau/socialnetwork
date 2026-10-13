# Werewolf service API (contract for the frontend)

Backend: `werewolf/backend` (FastAPI). Behind the gateway it is `/api/werewolf/*` (prefix stripped) and
`/api/werewolf/ws/{code}` for the WebSocket. Game rules, abilities, night order and win conditions are the ones of the
original 3-faction game (Người / Sói / Ma, 11 abilities, 5-40 players); `GET /setup/meta` returns the rule texts so the UI
never hard-codes them.

## Conventions

- **Auth**: the center JWT cookie (`sn_token`). A human seat is `(user_id, username)` from the token; there are no
  player tokens and no free-text names. Missing/invalid cookie: REST `401 {"detail": "Not authenticated"}`, WebSocket
  closed with 1008. `GET /setup/meta`, `GET /setup/random` and `/health` are public.
- **Cross-site writes**: every `POST` goes through the same Origin check as center: if an `Origin` header is present it
  must be in `ALLOWED_ORIGINS`, else `403 {"detail": "Origin not allowed"}`. The WebSocket requires an allowed `Origin`
  (a missing one is refused). Always send requests from the app origin with `credentials: "include"`.
- **Room code**: 5 letters (`^[A-Za-z]{5}$`, case-insensitive; the server returns it upper-case). It is the room id.
- **Seat number**: a player's id in the game is the seat number, 1..N. Seat 1 is the creator of the room. Every
  `target`, `author.id`, `me.id` and `players[].id` is a seat number; `0` means "nobody" (abstain / no target).
- **Errors** (`{"detail": "<message>"}`, messages are Vietnamese, show them as is):
  `400` invalid action/chat (wrong phase, bad target, text empty/too long/too fast), `401` not logged in, `403` not
  allowed (not host, not seated, peeking while alive, origin), `404` unknown room, `409` wrong room state (not started,
  already started, room full, already in the room, 3-room cap, code taken), `422` validation (body/params),
  `429` rate limited, `503` server has the maximum number of rooms.
- **Rate limits** (per user, all tabs together): REST 60 calls/10 s, room creation 6/min, join attempts 15/min,
  chat 8 messages/10 s (plus 0.8 s between two messages of a game), WebSocket 20 frames/10 s (beyond it the socket is
  closed with 1008). Other limits: 3 live rooms per user, 200 rooms per server, 40 seats per room, 500 sockets.
- Field names: room/game payloads are camelCase (as in the original), the list and history endpoints are snake_case.
- Rooms live in memory (lost on restart). A room with nobody connected is deleted after 30 min idle (5 min once its game
  finished).

## Privacy (enforced on the server)

- A **living** player receives exactly their own perspective: their own faction/ability, what they have been told
  (their private night notes, public findings, wolves know each other and wolf-only findings), public chat, and the wolf
  channel only if they are a wolf.
- The **full log** (every action with names and factions) and **other players' perspectives**
  (`GET .../perspective/{seat}`) are available only to players who are **dead**, and to everybody once the game is
  **over** (then `players[]` also shows every faction and ability). The host gets no extra view.
- Lobby: a member only sees the role of their own seat (`members[].faction/ability`, `null` for all other seats).
  A non-member previewing a lobby sees no roles. The same state is used by REST, WebSocket and after a rematch.
- Chat: `public` only by day (and for the dead when `deadTalk`), `wolf` only to wolves at night, `dead` only to the dead
  when `deadTalk` is false. Chat text is plain text: render it as text, never as HTML (the server strips control and
  bidi characters and collapses whitespace but does not escape HTML).

## Objects

### Room state (`state`)

```jsonc
{
  "code": "ABCDE", "title": "Làng Trăng Máu",
  "isHost": true,
  "you": {"username": "alice", "seat": 1},          // null for a non-member previewing a lobby
  "minPlayers": 5, "maxPlayers": 40,
  "members": [                                       // one per seat, in seat order; no roles except your own (lobby only)
    {"seat": 1, "name": "alice", "isBot": false, "isHost": true, "isYou": true,
     "faction": {"code": "WOLF", "label": "Sói"} | null,      // only your own seat, only before the game starts, only if set up
     "ability": {"code": "KILL", "label": "Giết trực tiếp"} | null}
  ],
  "timer": 0,            // seconds per night turn (day = 2x); 0 = off
  "events": true, "deadTalk": true, "listed": true,
  "history": {"games": 3, "VILLAGER": 1, "WOLF": 1, "GHOST": 0, "draw": 1},   // wins per faction in this room
  "started": true,
  "game": null | Game  // null in the lobby (and for non-members)
}
```

Every route that returns a state wraps it: `{"id": "ABCDE", "state": <Room state>}`.

### Game (`state.game`, also what `perspective` returns)

```jsonc
{
  "phase": "night" | "revenge" | "day" | "settle" | "over",   // "setup" never reaches clients
  "night": 2,                      // current night/day number
  "gameOver": false,
  "winner": {"code": "WOLF", "label": "Sói"} | null,          // null + gameOver = draw
  "me": {"id": 3, "name": "alice", "alive": true,
         "faction": {"code": "VILLAGER", "label": "Người"}, "ability": {"code": "SEE_FACTION", "label": "Xem nhóm"}},
  "players": [{"id": 1, "name": "An", "alive": true, "isBot": true,
               "faction": {...} | null, "ability": {...} | null}],   // faction/ability only when known to you; all known when gameOver
  "actions": [                      // what you may/must do now (empty if nothing)
    {"kind": "night" | "wolf" | "day" | "revenge",
     "options": [2, 5, 7],          // legal target seats
     "submitted": false, "current": 5 | null, "canAbstain": false}      // current: your choice (0 = abstain)
  ],
  "waitingFor": 2,                  // how many players still have to act
  "log": [{"round": "Đêm 1", "text": "..."}],   // YOUR log; full log only for the dead / when over
  "event": {"code": "FOG", "icon": "🌫️", "title": "Sương mù", "text": "...", "affectsDay": false} | null,
  "recap": {"seq": 4, "kind": "dawn" | "dusk", "round": 2,
            "deaths": [{"id": 4, "name": "Bình", "cause": "bị giết ban đêm",
                        "revealed": {"faction": {...}, "ability": {...}}}]} | null,   // "revealed" only with "Lộ info khi chết"; show the card when seq changes
  "timer": {"total": 60, "secondsLeft": 41.5} | null,    // secondsLeft is a snapshot at send time: count down locally
  "chat": [{"seq": 12, "round": "Ngày 1", "channel": "public" | "wolf" | "dead", "text": "...",
            "target": 0, "dead": false, "author": {"id": 2, "name": "Cường"}}],  // snapshot, last 120 you may read
  "chatChannel": "public" | "wolf" | "dead" | null       // where YOUR next message would go; null = cannot chat now
}
```

Turn rules the UI needs: night: `night` action (your ability) and, for wolves, a `wolf` action (the night kill vote,
`target` 0 = abstain; `canAbstain` true). Day: every living player has a `day` action (vote, 0 = abstain). A dying
player with *Giết khi chết* gets a `revenge` action. Actions of one phase are simultaneous; the phase advances when
everybody has chosen (bots choose instantly) or when the host forces it or the timer runs out.

### Room summary (`GET /rooms`) and history entry: see below.

## REST

### Setup (public)

- `GET /setup/meta` ->
  `{"minPlayers":5,"maxPlayers":40,"maxRoomsPerUser":3,"defaults":{"VILLAGER":[{icon,label,hint}],"WOLF":[...],"GHOST":[...]},
  "factions":[{"code","label"}],"abilities":[{"code","label","help","allowedFactions":["VILLAGER",...]}],
  "help":{"rules":[{icon,title,text}],"events":[{code,icon,title,text,affectsDay}]},"timerOptions":[0,30,60,90],
  "timerRange":[5,600],"chat":{"maxLength":140,"minIntervalSeconds":0.8,"keep":400}}`.
  Faction codes: `VILLAGER` (Người), `WOLF` (Sói), `GHOST` (Ma). Ability codes: `NONE, BLOCK_EFFECTS, REVERSE_EFFECTS,
  BLOCK_ABILITY, REVERSE_ABILITY, KILL, KILL_ON_DEATH, SEE_FACTION, SEE_ABILITY, REVEAL_ON_DEATH, TRANSFORM`.
- `GET /setup/random?count=5..40` -> `{"seats":[{"faction":"WOLF","ability":"KILL"}, ...]}` (balanced deal, shuffled;
  editable by the client; seat 1 becomes the host's role). `422` outside 5..40.

### Rooms (cookie auth)

| Route | Body | Result |
|---|---|---|
| `POST /rooms` | `CreateBody` (optional, `{}` is valid) | `201 {id, state}` |
| `GET /rooms` | - | `[RoomSummary]` open lobbies |
| `GET /rooms/{code}` | - | `{id, state}`; `403` if you are not seated and the game is running |
| `POST /rooms/{code}/join` | - | `{id, state}`; you replace one bot seat and keep its role |
| `POST /rooms/{code}/leave` | - | `{"left": true}`; your seat becomes a bot, host moves to another human, room deleted when no human is left |
| `POST /rooms/{code}/start` | - | `{id, state}` host only |
| `POST /rooms/{code}/bots` | `{"count": 1..39}` | `{id, state}` host only, lobby only, max 40 seats |
| `POST /rooms/{code}/action` | `{"target": 0.., "kind": "ability"\|"wolf"}` | `{id, state}` |
| `POST /rooms/{code}/chat` | `{"text": "...", "target": 0}` | `{id, message}` (the entry as in `chat[]`) |
| `POST /rooms/{code}/force` | - | `{id, state}` host only: skip whoever has not chosen |
| `POST /rooms/{code}/rematch` | - | `{id, state}` host only, game must be over; new random deal, same people |
| `POST /rooms/{code}/reset` | - | `{id, state}` host only: back to the lobby (bots removed, 5 seats minimum, roles cleared) |
| `GET /rooms/{code}/perspective/{seat}` | - | the `Game` object as seat `seat` sees it; `403` while you are alive and the game is not over; `409` before start; `404` bad seat |

`CreateBody` (all optional):
```jsonc
{
  "count": 12,                       // 5..40 seats; roles dealt at random when the game starts
  "seats": [{"faction": "WOLF", "ability": "KILL"}, ...],   // exact setup, one entry per seat, seat 1 = you; length = count
  "roomName": "Làng của tôi",        // <= 30 chars, empty = random title
  "roomCode": "WOLFS",               // 5 letters; 409 if taken; default random
  "start": false,                    // true = start now; remaining seats are bots
  "timerSeconds": 0,                 // 0 (off) or 5..600; the UI offers 0/30/60/90
  "events": true,                    // random night event cards
  "deadTalk": true,                  // dead players chat in the public channel (false: their own channel)
  "listed": true                     // false = joinable by code only, not in GET /rooms
}
```
With neither `count` nor `seats` the room has 5 seats. `seats` is validated against the rules (>=1 Sói and >=1 Người, ability
allowed for the faction, 5..40): `422` with the reason. `start` that fails (and nothing else) deletes the room again.
"Open lobby" = `start:false`; other users then `join` by code, each replacing one bot seat (the one named like them, else a
random one) and inheriting that seat's role. Roles stay preset only while every seat has one: adding bots re-deals at start.

`RoomSummary` (`GET /rooms`, snake_case): `{"id","title","host","players","seats","open_seats","max_players","timer","events"}`
(`players` = humans, `open_seats` = bot seats a joiner can take; only listed, not-started lobbies with a free seat; 50 max,
most recent first).

### History

`GET /me/history?limit=1..100` (default 20) -> newest first, only games the caller played as a human:
```jsonc
[{"game_id": 17, "room_id": "ABCDE", "finished_at": "2026-10-13T08:00:00Z",
  "winner": "VILLAGER" | "WOLF" | "GHOST" | "DRAW",
  "days": 4, "size": 12,                               // nights played, seats (bots included)
  "your_faction": "WOLF", "your_ability": "KILL",      // the roles you STARTED with
  "your_outcome": "won" | "draw" | "lost", "won": true, // judged by your final faction (a wolf turned Ma is on the Ma side)
  "survived": false, "days_survived": 3,
  "players": [{"username": "alice", "faction": "WOLF", "ability": "KILL", "outcome": "won", "survived": false}]}]  // humans only
```
Bots are never stored. Rows written by the old 4-role game are mapped (`werewolf`->WOLF, `seer`->VILLAGER/SEE_FACTION...).
A user leaving mid-game still gets the result (their seat was played by a bot afterwards).

## WebSocket `/ws/{code}`

Connect with the cookie and an allowed `Origin` (browsers do). Refused (closed before the handshake completes, code 1008)
without a valid cookie/Origin, for a bad or unknown code, or if you hold no seat; 1013 when the server has too many sockets.
One socket per (room, user): a newer one closes the older with 1008. Token expiry closes the socket with 1008.
The socket is closed with 1008 if you leave the room (1001 when the room is deleted).

Server -> client frames (JSON text):
- `{"type":"state","state":<Room state>}` right after connecting and whenever anything changes for you (phase change,
  member joins/leaves, vote/action by anyone, timer expiry...). Identical consecutive frames are not re-sent.
- `{"type":"chat","message":<chat entry>}` for each new chat message you may read. It is *not* a state push; append it to
  `game.chat` (dedupe by `seq`; the next `state` carries the authoritative snapshot).
- `{"type":"error","error":"<message>"}` for a rejected frame (the socket stays open).

Client -> server frames (<= 8192 chars, 20 per 10 s):
- `{"type":"action","target":5,"kind":"ability"}` (`kind` `"ability"` default, or `"wolf"`; same rules as the REST route)
- `{"type":"chat","text":"...","target":0}` (`target` = seat the message is about, 0 = none; <= 140 chars after cleaning)
- `{"type":"force"}` host only
Anything else gets `{"type":"error","error":"Invalid message"}`. Lobby operations (create/join/leave/start/bots/rematch/
reset) and perspectives are REST only; REST `action`/`chat`/`force` also work and trigger the same pushes to sockets.

Timer: when `game.timer` is set the server forces the turn at 0 (unchosen players are skipped, bots act) and pushes
the new state; run the countdown locally from `secondsLeft`. Rooms without an open socket are not ticked.

## Differences from the original game

Rules are unchanged (engine ported as is, original tests ported). Deliberate changes: privacy (above); identity (user
seats instead of per-room tokens/names); a human joining takes a random bot seat (not the last one) so the host cannot tell
who got which role; a player who leaves is replaced by a bot instead of stalling the game.
