# Lab API

Microservice lab: three communication patterns with real services.

| Pattern | Services |
|---|---|
| gRPC + Redis cache-aside | `lab-user` (gRPC :50051, internal), Redis |
| Work queue with retry and dead-letter queue | RabbitMQ + `lab-worker` |
| Event log with replay | Kafka + `lab-worker` |

RabbitMQ, Kafka and `lab-worker` run only under the compose profile `messaging` (off by default, about
0.7-1.3 GB of RAM). The app works without them: `/status` shows them down and their endpoints answer `503`.

Served at `/api/lab/` (prefix stripped by the gateway), same origin. Auth: center JWT cookie `sn_token`
(`401` otherwise, including `/status`). Unsafe routes (POST/DELETE) also check `Origin` (`403` for a disallowed one).
Errors are `{"detail": "<message>"}` (a string; validation errors are `422 {"detail": "Dữ liệu không hợp lệ."}`;
the 401/403 bodies come from the shared auth code and are English). JSON bodies only; unknown fields are rejected (`422`).

| Method | Path | Result |
|---|---|---|
| GET | `/health` | `200 {"status":"ok"}` (public) |
| GET | `/status` | `200 {"redis","grpc","rabbitmq","kafka","messaging": bool}` |
| GET | `/users/{id}` | `200 {"id","name","source":"cache"\|"grpc","ms":int}`; `503` gRPC down |
| DELETE | `/users/{id}/cache` | `204` |
| POST | `/notifications` | `202 {"id":int}`; `503` RabbitMQ down (nothing stored) |
| GET | `/notifications?limit=20` | `200` list, newest first, own rows only (`limit` 1..100) |
| POST | `/logs` | `202 {"id":int}`; `503` Kafka down |
| GET | `/logs?limit=50` | `200` list, newest first, own rows only (`limit` 1..100) |
| GET | `/logs/replay?limit=50` | `200 {"fromBeginning":true,"messages":[...]}`; `503` Kafka down (`limit` 1..200) |
| DELETE | `/events` | `204`, deletes all own `lab_events` rows |

Writes (every POST and DELETE) are limited to 30 per minute per user: `429 {"detail": ...}`.

## status

Each probe has a 1 s timeout and never raises. `messaging` is `rabbitmq && kafka`.

## users (gRPC + Redis cache-aside)

`id` is 1..16 characters `[0-9A-Za-z]` (otherwise `422`). The demo directory knows `1` Alice, `2` Bob,
`3` Charlie; anything else is `Unknown`. The route looks in Redis (`lab:user:{id}`, TTL 300 s, shared by all users:
public demo data) and on a miss calls `lab-user` over ONE reused gRPC channel (2 s timeout), then stores the result.
`source` says which one answered, `ms` is the server-side time. A Redis outage only costs speed (always `grpc`);
`503` only when gRPC is down and the value is not cached.

## notifications (RabbitMQ)

Request `{"title": 1..80 chars, "body": 1..300 chars}`. The row is stored with status `queued`, then
`{"id","userId","title","body"}` is published (persistent, publisher confirms) to the durable queue
`lab.notifications` (max length 1000, dead-letter exchange -> `lab.notifications.dlq`). The worker consumes with
manual ack and prefetch 5: `processing` -> `done` after a simulated 300-800 ms of work. A title starting with
`[fail]` makes the processing fail: 3 attempts with exponential backoff (status `retrying` between attempts,
`attempts` counted in the row), then the message is rejected to the DLQ and the status becomes `dead`.

```json
{"id": 1, "title": "Hi", "body": "there", "status": "queued", "attempts": 0,
 "createdAt": "2026-01-01T00:00:00Z", "processedAt": null}
```

`status` is one of `queued`, `processing`, `retrying`, `done`, `dead`. Poll the list to watch it change.

## logs (Kafka)

Request `{"level": "info"|"warn"|"error", "message": 1..200 chars}`. Produced as JSON
`{"userId","level","message"}` to the topic `lab.logs` (1 partition), keyed by the user id, `acks=all`.
`id` in the `202` is the Kafka offset of the message. The worker (consumer group `lab-log-writer`, auto commit off,
commit after the DB write) stores each message with its partition and offset (a redelivery is stored once).

```json
{"id": 1, "level": "warn", "message": "disk", "createdAt": "2026-01-01T00:00:00Z", "partition": 0, "offset": 41}
```

`GET /logs/replay` starts a FRESH consumer without a group, assigns the partition, seeks to the beginning and reads
for at most 3 s overall; it returns only messages keyed to the caller (oldest first, up to `limit`):

```json
{"fromBeginning": true, "messages": [{"offset": 41, "partition": 0, "level": "warn", "message": "disk", "timestamp": "2026-01-01T00:00:00+00:00"}]}
```

## Data

Table `lab_events(id, user_id idx, kind, title, body, status, attempts, kafka_partition, kafka_offset, created_at,
processed_at)`; `title`/`body` hold the notification title/body or the log level/message. Message bodies are never
logged. Queue and topic names are fixed server side (nothing user-controlled).

Account events: deleting a user in center deletes their `lab_events` rows (idempotent). Messages already in Kafka
cannot be deleted: they carry the numeric user id as key and no name, and expire by retention (1 hour).
