# Face API

Browser-side face symmetry measurement (MediaPipe; video never leaves the device). The backend stores
**only numeric scores** on an explicit opt-in: no images, landmarks, skin metrics or username.

Served at `/api/face/` (prefix stripped by the gateway). Auth: center JWT cookie `sn_token` (401 otherwise).
Unsafe routes (POST/DELETE) also check `Origin`: a disallowed one gets `403 {"detail": "Origin not allowed"}`.

| Method | Path | Result |
|---|---|---|
| GET | `/health` | `200 {"status":"ok"}` (public) |
| POST | `/measurements` | `201` measurement |
| GET | `/measurements?limit=50` | `200` list, newest first, own rows only (`limit` 1..200) |
| DELETE | `/measurements/{id}` | `204`; `404` for unknown or someone else's id (same body) |
| DELETE | `/measurements` | `204`, deletes all own rows |

Request body of POST (extra fields rejected with 422):

```json
{"symmetry": 0, "eye": null, "nose": null, "mouth": null, "ear": null, "angle": null}
```

`symmetry` int 0..100 (required); `eye`, `nose`, `mouth`, `ear` int 0..100 or null; `angle` float 0..90 or null.

Measurement:

```json
{"id": 1, "createdAt": "2026-01-01T00:00:00Z", "symmetry": 87, "eye": 90, "nose": 80, "mouth": 85, "ear": 70, "angle": 12.5}
```

Limits: at most 200 rows per user (the oldest are deleted in the same transaction when exceeded); POST and
DELETE are limited to 30 writes per minute per user (`429 {"detail": ...}`).

Account events: deleting a user in center deletes all their measurements; renaming is a no-op.
