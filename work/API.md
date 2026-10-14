# Work API (contract for the frontend)

Base URL through the gateway: `/api/work` (the gateway strips the prefix; paths below are backend paths).
Auth: the `sn_token` cookie from center (`credentials: "same-origin"`), except `POST /telnyx/webhook`.
Unsafe methods (POST/DELETE) also check the `Origin` header (a present foreign Origin gives 403 `Origin not allowed`).
Errors are `{"detail": "<Vietnamese text>"}` (422 validation errors have the FastAPI list form).
Writes: 60 per minute per user, otherwise 429 `Bạn thao tác quá nhanh, hãy thử lại sau` (database reads: 240/min).
Every operation of one user is serialised; if it waits too long the answer is 429 `Cơ sở dữ liệu đang bận, hãy thử lại sau`
(or `Hệ thống đang bận, hãy thử lại sau` for files).

Common: `401` not signed in. Nothing here ever takes a path from a URL segment except the table name of
`GET /db/tables/{name}` (validated against the user's own database).

## Files

Virtual paths start with `/` (`/`, `/docs`, `/docs/a.txt`), one optional trailing `/`. Rules for each component: NFC-normalised,
1-100 chars, not `.`/`..`, no control/bidi/zero-width characters, none of `/ \ : * ? " < > |` or NUL, no trailing dot or space,
not a Windows reserved name (`con`, `nul`, `com1`..., with or without extension). Depth <= 6 (a file at `/a/b/c/d/e/f.txt`
is the deepest). Whole path <= 700 chars. Invalid: `400` with one of
`Đường dẫn không hợp lệ`, `Tên không hợp lệ`, `Tên phải dài từ 1 đến 100 ký tự`, `Tên chứa ký tự không được phép`,
`Tên không được kết thúc bằng dấu chấm hoặc dấu cách`, `Tên này là tên dành riêng của hệ thống`, `Đường dẫn quá sâu (tối đa 6 cấp)`.
Symbolic links are never followed (400). Another user's data simply does not exist (404).

Limits: file <= 20 MB, quota 100 MB per user, <= 500 entries per folder (also the listing cap), <= 1000 files+folders per user.

### GET /files?path=/
`200`
```json
{"path": "/", "entries": [{"name": "docs", "type": "folder", "size": 0, "modifiedAt": 1760000000},
                          {"name": "a.txt", "type": "file", "size": 5, "modifiedAt": 1760000100}],
 "usage": {"usedBytes": 5, "quotaBytes": 104857600}}
```
Folders first, then files, each sorted by name (case-insensitive). `modifiedAt` is Unix seconds. `path` defaults to `/`.
Errors: 404 `Không tìm thấy tệp hoặc thư mục`; 400 `Đường dẫn không phải thư mục`.

### POST /files/folder
Body `{"path": "/docs", "name": "reports"}` (no other fields) -> `201 {"name": "reports"}`.
Errors: 409 `Tên này đã tồn tại`, 409 `Thư mục đã đầy (tối đa 500 mục)`, 409 `Đã đạt số tệp và thư mục tối đa (1000)`, 404, 400 as above.

### POST /files/upload?path=/docs
`multipart/form-data`, field `file` (`Content-Length` required: 411 otherwise; > 20 MB + framing -> 413). The name is the
last part of the client filename (anything before a `/` or `\` is dropped) and is validated like any name.
`201 {"name": "a.txt", "size": 5}`. Never overwrites.
Errors: 409 `Tên này đã tồn tại` (and the two 409 limits above), 413 `Tệp lớn hơn 20 MB`, 413 `Vượt quá dung lượng 100 MB`,
404 (folder missing), 400 (target is not a folder / bad name / too deep), 422 (no `file` field).

### GET /files/download?path=/docs/a.txt
`200`, bytes of the file with `Content-Type: application/octet-stream`, `Content-Disposition: attachment; filename=...`,
`X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox`, `Cache-Control: private, no-store`. Never shown inline:
use a link/`download`, not an `<iframe>`/`<img>`. Errors: 404 `Không tìm thấy tệp` (also for folders and `/`), 400.

### DELETE /files?path=/docs/a.txt
`204`. A folder is deleted with everything inside. Errors: 400 `Không thể xóa thư mục gốc`, 404,
409 `Thư mục có quá nhiều mục để xóa cùng lúc` (> 2000 entries).

### POST /files/rename
Body `{"path": "/docs/a.txt", "newName": "b.txt"}` -> `200 {"name": "b.txt"}` (same folder; renaming to the same name is a no-op).
Errors: 409 `Tên này đã tồn tại`, 400 `Không thể đổi tên thư mục gốc` / bad name, 404.

## Database (a private SQLite file per user, max 20 MB)

### GET /db/tables
`200 [{"name": "people", "rows": 3}]` (user tables only, at most 200, sorted by name; `[]` when nothing exists yet).

### GET /db/tables/{name}?page=1&pageSize=50&q=
`pageSize` 1..200 (default 50), `page` >= 1, `q` <= 200 chars (case-insensitive substring, matched literally on every column).
```json
{"columns": ["id", "name"], "rows": [[1, "An"], [2, "Bình"]], "total": 2, "page": 1, "pageSize": 50}
```
Errors: 404 `Không tìm thấy bảng`, 422 for out-of-range query values.
Cells: `null`, numbers, or strings; blobs appear as `"<blob 12 bytes>"`, integers beyond 2^53 and non-finite floats as strings,
text longer than 2000 characters is cut with `…`.

### POST /db/query
Body `{"sql": "SELECT * FROM people"}` (1..10000 chars) -> `200`
```json
{"columns": ["id", "name"], "rows": [[1, "An"]], "rowCount": 1, "changes": 0, "truncated": false}
```
`rowCount` = rows returned (<= 1000; `truncated` is true when there were more), `changes` = rows modified. One statement
only (a trailing `;` and comments are fine). The statement runs in its own transaction: on any error nothing is changed.
Allowed first words: SELECT, WITH, INSERT, UPDATE, DELETE, REPLACE, CREATE, DROP, ALTER, VALUES, EXPLAIN, PRAGMA
(only `table_info`, `table_xinfo`, `index_list`, `index_info`, `foreign_key_list`).
Not allowed: ATTACH, DETACH, VACUUM, REINDEX, ANALYZE, other PRAGMAs, virtual tables, BEGIN/COMMIT/SAVEPOINT, `load_extension`
and file functions. Aborted after about 3 seconds. Values longer than 1,000,000 bytes are refused.
All SQL problems are `400 {"detail": ...}`:
`Câu lệnh SQL trống`, `Câu lệnh SQL quá dài (tối đa 10000 ký tự)`, `Câu lệnh SQL chứa ký tự không hợp lệ`,
`Loại câu lệnh này không được phép`, `Chỉ được chạy một câu lệnh mỗi lần`,
`Thao tác này không được phép trong khung thử nghiệm`, `Truy vấn chạy quá lâu (quá 3 giây) nên đã bị dừng`,
`Cơ sở dữ liệu vượt quá giới hạn 20 MB hoặc dữ liệu quá lớn`, or `Lỗi SQL: <sqlite message without paths, <= 200 chars>`
(for example `Lỗi SQL: no such table: x`). 422 when `sql` is missing/too long for the schema. 500 `Không mở được cơ sở dữ liệu` is unexpected.

### POST /db/import
`multipart/form-data`: `file` (CSV, UTF-8, <= 2 MB) and `table` (`[A-Za-z_][A-Za-z0-9_]{0,63}`, not starting with `sqlite_`).
First row = column names (1..64 printable chars, unique ignoring case, <= 50 columns); every column is `TEXT`; <= 20000 data rows;
short rows are padded with empty strings; empty lines are skipped; a UTF-8 BOM is accepted. `Content-Length` required (411).
`201 {"table": "people", "rows": 2}`. Errors: 400 `Tên bảng chỉ gồm chữ, số, dấu gạch dưới, bắt đầu bằng chữ (tối đa 64 ký tự)`,
`Tệp CSV phải mã hóa UTF-8`, `Tệp CSV chứa ký tự không hợp lệ`, `Tệp CSV cần dòng đầu là tên cột`, `Tối đa 50 cột`,
`Tên cột không hợp lệ (1-64 ký tự, không rỗng)`, `Tên cột bị trùng`, `Có dòng nhiều ô hơn số cột`, `Tệp CSV không hợp lệ`;
409 `Bảng này đã tồn tại`, `Đã đạt số bảng tối đa (50)`; 413 `Tệp CSV lớn hơn 2 MB`, `Tối đa 20000 dòng`,
`Cơ sở dữ liệu vượt quá giới hạn 20 MB`. Nothing is created when it fails.

### GET /db/export?table=people
`200` CSV (`text/csv; charset=utf-8`, CRLF, header row first) with `Content-Disposition: attachment; filename="people.csv"`
and `nosniff`. Text cells starting with `=`, `+`, `-`, `@`, tab or CR (and such column names) get a leading `'` (spreadsheet
formula guard); real numbers and NULL (empty) are untouched. 404 `Không tìm thấy bảng`.

### DELETE /db
`204`. Drops the user's whole database file (also when none exists).

## Telnyx calls

### POST /telnyx/webhook (public, not for the browser)
Called by Telnyx only. Headers `telnyx-signature-ed25519` (base64) and `telnyx-timestamp` (Unix seconds, within 5 minutes);
signature over `<timestamp>|<raw body>`; public key = env `TELNYX_PUBLIC_KEY` (base64). No cookie, no Origin check, body <= 256 KB.
`503 Webhook Telnyx chưa được cấu hình` (no key), `401 Chữ ký không hợp lệ` (missing/old/bad), `413`, `400 Sự kiện không hợp lệ`
(signed but not an event). Success `200` with `{"status": "ok" | "duplicate" | "ignored"}`.
Handled `data.event_type`: `call.initiated` (answer the call), `call.answered` (speak `TELNYX_GREETING`, then start recording),
`call.recording.saved` (metadata only; nothing is downloaded). Other types are acknowledged and ignored. Duplicate `data.id`
is acknowledged without acting again. API calls need `TELNYX_API_KEY` (5 s timeout; failures are logged by type only and do
not fail the webhook). The WebSocket media-stream receiver and the outbound-SMS script of the original are **not ported**.

### GET /calls?limit=50 (admin only)
`limit` 1..200. `403 Chỉ quản trị viên được xem danh sách cuộc gọi` unless the token role is `admin`. Newest first:
```json
[{"id": 7, "eventType": "call.answered", "callControlId": "v3:abc", "from": "*********67", "to": "**********34",
  "payloadSize": 412, "createdAt": "2026-10-14T08:00:00+00:00"}]
```
Numbers keep only their last 2 digits (digits are `*`-masked); the stored table `call_events` keeps nothing else about the caller.
At most the newest 5000 events are kept.
