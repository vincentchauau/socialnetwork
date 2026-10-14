"""SQLite sandbox: one private database file per user, never the platform's Postgres.

Every function here is synchronous and meant to run in a worker thread under `store.user_lock(user_id)`.
User SQL runs on a connection that is locked down:
- `set_authorizer` denies ATTACH, DETACH, virtual tables, transaction control, every PRAGMA except a few
  read-only schema ones, and the functions that could touch files or load code;
- exactly one statement (Python's sqlite3 refuses a second one, even after a ';');
- extension loading is off, `trusted_schema` is off, size limits (value length, columns, expression depth...) are set;
- `max_page_count` caps the file at 20 MB, a progress handler aborts after about 3 seconds;
- explicit transaction (`isolation_level=None` and our own BEGIN / COMMIT / ROLLBACK).
"""

import csv
import io
import math
import re
import sqlite3
import time
from pathlib import Path

MAX_DB_BYTES = 20 * 1024 * 1024
QUERY_SECONDS = 3.0
IMPORT_SECONDS = 10.0
MAX_SQL_CHARS = 10_000
MAX_ROWS = 1000
MAX_CELL_CHARS = 2000
MAX_TABLES = 50
MAX_LIST_TABLES = 200
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 20_000
MAX_IMPORT_COLUMNS = 50
MAX_PAGE_SIZE = 200
MAX_SAFE_INT = 2**53
PROGRESS_STEPS = 5000
MAX_ERROR_CHARS = 200

SAFE_PRAGMAS = frozenset({"table_info", "table_xinfo", "index_list", "index_info", "foreign_key_list"})
DENIED_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"})
DENIED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_CREATE_VTABLE,
        sqlite3.SQLITE_DROP_VTABLE,
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_SAVEPOINT,
    }
)
ALLOWED_FIRST_WORDS = frozenset(
    {"select", "with", "insert", "update", "delete", "replace", "create", "drop", "alter", "values", "explain", "pragma"}
)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
LEADING_NOISE = re.compile(r"\s+|--[^\n]*(\n|\Z)|/\*.*?(\*/|\Z)", re.DOTALL)
PATH_LIKE = re.compile(r"([A-Za-z]:)?[\\/][^\s'\"]*")

LIMITS = (
    (sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000),
    (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20_000),
    (sqlite3.SQLITE_LIMIT_COLUMN, 100),
    (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100),
    (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20),
    (sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH, 500),
    (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 200),
    (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
)


class DbError(Exception):
    """A problem to report to the user: HTTP status plus a Vietnamese message without internals."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _authorizer(action: int, arg1: str | None, arg2: str | None, _db: str | None, _source: str | None) -> int:
    if action in DENIED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA:
        return sqlite3.SQLITE_OK if (arg1 or "").lower() in SAFE_PRAGMAS else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in DENIED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _connect(path: Path, *, create: bool, seconds: float = QUERY_SECONDS) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + ("?mode=rwc" if create else "?mode=rw")
    try:
        conn = sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False, timeout=2.0)
    except sqlite3.Error:
        raise DbError(500, "Không mở được cơ sở dữ liệu") from None
    try:
        conn.enable_load_extension(False)
    except AttributeError:  # pragma: no cover - Python built without extension support: nothing to disable
        pass
    for category, value in LIMITS:
        conn.setlimit(category, value)
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    conn.execute(f"PRAGMA max_page_count = {MAX_DB_BYTES // page_size}")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA trusted_schema = OFF")
    conn.execute("PRAGMA foreign_keys = ON")
    deadline = time.monotonic() + seconds
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_STEPS)
    return conn


def _sanitise(error: Exception) -> str:
    text = str(error).lower()
    if "interrupted" in text:
        return "Truy vấn chạy quá lâu (quá 3 giây) nên đã bị dừng"
    if "full" in text or "too big" in text or "string or blob too big" in text:
        return "Cơ sở dữ liệu vượt quá giới hạn 20 MB hoặc dữ liệu quá lớn"
    if "not authorized" in text or "authoriz" in text:
        return "Thao tác này không được phép trong khung thử nghiệm"
    cleaned = PATH_LIKE.sub("…", str(error)).strip()[:MAX_ERROR_CHARS] or "lỗi không xác định"
    return f"Lỗi SQL: {cleaned}"


def _first_word(sql: str) -> str:
    position = 0
    while True:
        match = LEADING_NOISE.match(sql, position)
        if not match or match.end() == position:
            break
        position = match.end()
    word = re.match(r"[A-Za-z]+", sql[position:])
    return word.group(0).lower() if word else ""


def cell(value: object) -> object:
    """A JSON-safe cell: blobs summarised, huge ints / non-finite floats as text, long text trimmed."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, bytes):
        return f"<blob {len(value)} bytes>"
    if isinstance(value, int):
        return value if abs(value) <= MAX_SAFE_INT else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    text = str(value)
    return text if len(text) <= MAX_CELL_CHARS else text[:MAX_CELL_CHARS] + "…"


def run_query(path: Path, sql: str) -> dict:
    if not sql.strip():
        raise DbError(400, "Câu lệnh SQL trống")
    if len(sql) > MAX_SQL_CHARS:
        raise DbError(400, "Câu lệnh SQL quá dài (tối đa 10000 ký tự)")
    if "\x00" in sql:
        raise DbError(400, "Câu lệnh SQL chứa ký tự không hợp lệ")
    if _first_word(sql) not in ALLOWED_FIRST_WORDS:
        raise DbError(400, "Loại câu lệnh này không được phép")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(path, create=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        before = conn.total_changes
        conn.set_authorizer(_authorizer)
        try:
            cursor = conn.execute(sql)
            fetched = cursor.fetchmany(MAX_ROWS + 1)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            cursor.close()
        finally:
            conn.set_authorizer(None)
        changes = conn.total_changes - before
        conn.execute("COMMIT")
    except sqlite3.ProgrammingError as error:
        _rollback(conn)
        if "one statement" in str(error):
            raise DbError(400, "Chỉ được chạy một câu lệnh mỗi lần") from None
        raise DbError(400, _sanitise(error)) from None
    except (sqlite3.Error, sqlite3.Warning) as error:
        _rollback(conn)
        if isinstance(error, sqlite3.Warning) and "one statement" in str(error):
            raise DbError(400, "Chỉ được chạy một câu lệnh mỗi lần") from None
        raise DbError(400, _sanitise(error)) from None
    finally:
        conn.close()
    truncated = len(fetched) > MAX_ROWS
    rows = [[cell(v) for v in row] for row in fetched[:MAX_ROWS]]
    return {"columns": columns, "rows": rows, "rowCount": len(rows), "changes": changes, "truncated": truncated}


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' "
        f"ORDER BY name LIMIT {MAX_LIST_TABLES}"
    )
    return [r[0] for r in rows]


def _open_existing(path: Path) -> sqlite3.Connection | None:
    return _connect(path, create=False) if path.is_file() else None


def list_tables(path: Path) -> list[dict]:
    conn = _open_existing(path)
    if conn is None:
        return []
    try:
        return [
            {"name": n, "rows": conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(n)}").fetchone()[0]}
            for n in _table_names(conn)
        ]
    except sqlite3.Error as error:
        raise DbError(400, _sanitise(error)) from None
    finally:
        conn.close()


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def browse(path: Path, name: str, page: int, page_size: int, q: str) -> dict:
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    page = max(1, page)
    conn = _open_existing(path)
    if conn is None:
        raise DbError(404, "Không tìm thấy bảng")
    try:
        if name not in _table_names(conn):
            raise DbError(404, "Không tìm thấy bảng")
        table = quote_identifier(name)
        columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        where, params = "", ()
        if q:
            clauses = [f"CAST({quote_identifier(c)} AS TEXT) LIKE ?1 ESCAPE '\\'" for c in columns]
            where = " WHERE " + " OR ".join(clauses) if clauses else " WHERE 0"
            params = (f"%{_like_escape(q)}%",) if clauses else ()
        total = conn.execute(f"SELECT COUNT(*) FROM {table}{where}", params).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(f"SELECT * FROM {table}{where} LIMIT {page_size} OFFSET {offset}", params).fetchall()
    except sqlite3.Error as error:
        raise DbError(400, _sanitise(error)) from None
    finally:
        conn.close()
    return {
        "columns": columns,
        "rows": [[cell(v) for v in row] for row in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def validate_table_name(name: str) -> str:
    if not TABLE_NAME.match(name) or name.lower().startswith("sqlite_"):
        raise DbError(400, "Tên bảng chỉ gồm chữ, số, dấu gạch dưới, bắt đầu bằng chữ (tối đa 64 ký tự)")
    return name


def _parse_csv(data: bytes) -> tuple[list[str], list[list[str]]]:
    if len(data) > MAX_IMPORT_BYTES:
        raise DbError(413, "Tệp CSV lớn hơn 2 MB")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DbError(400, "Tệp CSV phải mã hóa UTF-8") from None
    if "\x00" in text:
        raise DbError(400, "Tệp CSV chứa ký tự không hợp lệ")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if not header or not any(h.strip() for h in header):
            raise DbError(400, "Tệp CSV cần dòng đầu là tên cột")
        if len(header) > MAX_IMPORT_COLUMNS:
            raise DbError(400, "Tối đa 50 cột")
        names = [h.strip() for h in header]
        if any(not n or len(n) > 64 or not n.isprintable() for n in names):
            raise DbError(400, "Tên cột không hợp lệ (1-64 ký tự, không rỗng)")
        if len({n.casefold() for n in names}) != len(names):
            raise DbError(400, "Tên cột bị trùng")
        rows: list[list[str]] = []
        for row in reader:
            if not row:
                continue
            if len(row) > len(names):
                raise DbError(400, "Có dòng nhiều ô hơn số cột")
            if len(rows) >= MAX_IMPORT_ROWS:
                raise DbError(413, "Tối đa 20000 dòng")
            rows.append(row + [""] * (len(names) - len(row)))
    except csv.Error:
        raise DbError(400, "Tệp CSV không hợp lệ") from None
    return names, rows


def import_csv(path: Path, table: str, data: bytes) -> dict:
    validate_table_name(table)
    names, rows = _parse_csv(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(path, create=True, seconds=IMPORT_SECONDS)
    try:
        existing = _table_names(conn)
        if table in existing:
            raise DbError(409, "Bảng này đã tồn tại")
        if len(existing) >= MAX_TABLES:
            raise DbError(409, "Đã đạt số bảng tối đa (50)")
        columns = ", ".join(f"{quote_identifier(n)} TEXT" for n in names)
        marks = ", ".join("?" for _ in names)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(f"CREATE TABLE {quote_identifier(table)} ({columns})")
            conn.executemany(f"INSERT INTO {quote_identifier(table)} VALUES ({marks})", rows)
            conn.execute("COMMIT")
        except BaseException:
            _rollback(conn)
            raise
    except sqlite3.Error as error:
        if "full" in str(error).lower():
            raise DbError(413, "Cơ sở dữ liệu vượt quá giới hạn 20 MB") from None
        raise DbError(400, _sanitise(error)) from None
    finally:
        conn.close()
    return {"table": table, "rows": len(rows)}


def guard_formula(value: object) -> object:
    """Spreadsheet formula guard: a text cell starting with = + - @ (or tab / CR) gets a leading apostrophe."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def export_csv(path: Path, table: str) -> bytes:
    conn = _open_existing(path)
    if conn is None:
        raise DbError(404, "Không tìm thấy bảng")
    try:
        if table not in _table_names(conn):
            raise DbError(404, "Không tìm thấy bảng")
        cursor = conn.execute(f"SELECT * FROM {quote_identifier(table)}")
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow([guard_formula(d[0]) for d in cursor.description])
        for row in cursor:
            writer.writerow([guard_formula(cell(v)) for v in row])
    except sqlite3.Error as error:
        raise DbError(400, _sanitise(error)) from None
    finally:
        conn.close()
    return out.getvalue().encode("utf-8")


def delete_database(path: Path) -> None:
    """Drop the user's whole database file (idempotent)."""
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
