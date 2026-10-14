import csv
import io
import sqlite3
import time

import pytest

from app import sqlbox
from app.store import db_path
from tests.conftest import auth_cookie


def sql(client, headers, text):
    return client.post("/db/query", json={"sql": text}, headers=headers)


def seed(client, headers):
    assert sql(client, headers, "CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, note TEXT)").status_code == 200
    assert sql(client, headers, "INSERT INTO people (name, note) VALUES ('An', 'x'), ('Bình', '100%'), ('Chi', 'a_b')").status_code == 200


def upload_csv(client, headers, text, table="data", name="d.csv"):
    data = text.encode() if isinstance(text, str) else text
    return client.post("/db/import", data={"table": table}, files={"file": (name, data, "text/csv")}, headers=headers)


def test_requires_login(client):
    assert client.get("/db/tables").status_code == 401
    assert client.post("/db/query", json={"sql": "select 1"}).status_code == 401
    assert client.get("/db/export", params={"table": "t"}).status_code == 401
    assert client.delete("/db").status_code == 401


def test_empty_database_lists_nothing_and_creates_no_file(client, alice):
    assert client.get("/db/tables", headers=alice).json() == []
    assert client.get("/db/tables/nope", headers=alice).status_code == 404
    assert client.get("/db/export", params={"table": "nope"}, headers=alice).status_code == 404
    assert not db_path(1).exists()


def test_query_result_shape(client, alice):
    seed(client, alice)
    r = sql(client, alice, "SELECT id, name FROM people ORDER BY id")
    assert r.status_code == 200
    assert r.json() == {
        "columns": ["id", "name"],
        "rows": [[1, "An"], [2, "Bình"], [3, "Chi"]],
        "rowCount": 3,
        "changes": 0,
        "truncated": False,
    }
    update = sql(client, alice, "UPDATE people SET note = 'z'").json()
    assert update["changes"] == 3 and update["rows"] == [] and update["columns"] == []
    assert client.get("/db/tables", headers=alice).json() == [{"name": "people", "rows": 3}]


def test_failed_statement_rolls_back_and_error_is_a_400(client, alice):
    seed(client, alice)
    r = sql(client, alice, "INSERT INTO people (id, name) VALUES (1, 'dup')")
    assert r.status_code == 400 and "UNIQUE" in r.json()["detail"]
    bad = sql(client, alice, "SELECT * FROM missing_table")
    assert bad.status_code == 400 and "no such table" in bad.json()["detail"]
    syntax = sql(client, alice, "SELECT FROM WHERE")
    assert syntax.status_code == 400
    assert sql(client, alice, "SELECT count(*) FROM people").json()["rows"] == [[3]]


@pytest.mark.parametrize("text", ["SELECT 1; SELECT 2", "SELECT 1; DROP TABLE x", "SELECT 1;SELECT 2;", "SELECT 1; -- c\nSELECT 2"])
def test_only_one_statement(client, alice, text):
    r = sql(client, alice, text)
    assert r.status_code == 400 and "một câu lệnh" in r.json()["detail"]


def test_trailing_semicolon_and_comments_are_fine(client, alice):
    assert sql(client, alice, "/* hi */ SELECT 1 AS one; -- bye").json()["rows"] == [[1]]
    assert sql(client, alice, "  \n SELECT 2;  ").json()["rows"] == [[2]]


def test_second_statement_after_semicolon_never_runs(client, alice):
    seed(client, alice)
    assert sql(client, alice, "SELECT 1; DELETE FROM people").status_code == 400
    assert sql(client, alice, "SELECT count(*) FROM people").json()["rows"] == [[3]]


@pytest.mark.parametrize(
    "text",
    [
        "ATTACH DATABASE 'other.db' AS o",
        "ATTACH ':memory:' AS m",
        "DETACH DATABASE main",
        "PRAGMA writable_schema = ON",
        "PRAGMA journal_mode = DELETE",
        "PRAGMA max_page_count = 1000000",
        "PRAGMA database_list",
        "PRAGMA trusted_schema = ON",
        "SELECT load_extension('x')",
        "SELECT readfile('/etc/passwd')",
        "SELECT writefile('/tmp/x', 'y')",
        "SELECT fts3_tokenizer('simple')",
        "VACUUM INTO 'copy.db'",
        "VACUUM",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT a",
        "CREATE VIRTUAL TABLE v USING fts5(a)",
        "REINDEX",
        "ANALYZE",
        "",
        "   ",
        "-- only a comment",
    ],
)
def test_forbidden_statements(client, alice, text):
    r = sql(client, alice, text)
    assert r.status_code in (400, 422)
    detail = str(r.json()["detail"])
    assert "/" not in detail.replace("không", "") or r.status_code == 422


def test_safe_pragmas_are_allowed(client, alice):
    seed(client, alice)
    r = sql(client, alice, "PRAGMA table_info(people)")
    assert r.status_code == 200 and [row[1] for row in r.json()["rows"]] == ["id", "name", "note"]


def test_table_valued_pragmas_that_reveal_paths_are_denied(client, alice):
    for text in ("SELECT * FROM pragma_database_list", "SELECT * FROM pragma_page_count"):
        assert sql(client, alice, text).status_code == 400


def test_schema_changes_cannot_escape(client, alice):
    r = sql(client, alice, "CREATE TABLE sqlite_evil (a)")
    assert r.status_code == 400
    assert sql(client, alice, "UPDATE sqlite_master SET name = 'x'").status_code == 400


def test_recursive_cte_times_out(client, alice, monkeypatch):
    monkeypatch.setattr(sqlbox, "QUERY_SECONDS", 0.3)
    started = time.monotonic()
    r = sql(client, alice, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c")
    assert r.status_code == 400 and "quá lâu" in r.json()["detail"]
    assert time.monotonic() - started < 5
    assert sql(client, alice, "SELECT 1").status_code == 200  # the user is not locked out afterwards


def test_huge_result_is_truncated(client, alice):
    r = sql(client, alice, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 5000) SELECT x FROM c")
    body = r.json()
    assert r.status_code == 200 and body["truncated"] is True
    assert body["rowCount"] == 1000 and len(body["rows"]) == 1000


def test_exactly_the_row_limit_is_not_truncated(client, alice):
    r = sql(client, alice, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 1000) SELECT x FROM c")
    assert r.json()["truncated"] is False and r.json()["rowCount"] == 1000


def test_value_serialisation(client, alice):
    r = sql(client, alice, "SELECT X'0102' AS b, 9007199254740993 AS big, 1e999 AS inf, NULL AS n, 1.5 AS f, replace(hex(zeroblob(2000)), '0', 'a') AS long")
    row = r.json()["rows"][0]
    assert row[0] == "<blob 2 bytes>" and row[1] == "9007199254740993" and row[2] == "inf"
    assert row[3] is None and row[4] == 1.5 and len(row[5]) == sqlbox.MAX_CELL_CHARS + 1


def test_database_size_cap(client, alice, monkeypatch):
    sql(client, alice, "CREATE TABLE b (x BLOB)")
    full = False
    for _ in range(30):
        r = sql(client, alice, "INSERT INTO b SELECT zeroblob(900000) FROM (SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3)")
        if r.status_code == 400:
            full = True
            assert "20 MB" in r.json()["detail"]
            break
    assert full
    assert db_path(1).stat().st_size <= sqlbox.MAX_DB_BYTES + 8192


def test_single_value_length_limit(client, alice):
    r = sql(client, alice, "SELECT zeroblob(100000000)")
    assert r.status_code == 400 and "quá lớn" in r.json()["detail"]


def test_errors_never_contain_paths(client, alice):
    texts = ["SELECT * FROM nope", "ATTACH '/etc/passwd' AS x", "SELECT load_extension('/lib/evil.so')", "CREATE TABLE ("]
    for text in texts:
        detail = sql(client, alice, text).json()["detail"]
        assert "/etc" not in detail and "/lib" not in detail and "sqlite3" not in detail


def test_path_like_sqlite_messages_are_redacted():
    message = sqlbox._sanitise(sqlite3.OperationalError("unable to open /srv/data/work/db/1.sqlite3 and C:\\x\\y.db"))
    assert "srv" not in message and "C:" not in message and message.startswith("Lỗi SQL")
    assert sqlbox._sanitise(sqlite3.OperationalError("")).endswith("lỗi không xác định")


def test_sql_length_and_shape_validation(client, alice):
    assert sql(client, alice, "SELECT '" + "a" * 10000 + "'").status_code == 422
    assert sql(client, alice, "SELECT 1 /*" + "a" * 9985 + "*/").status_code == 200
    assert client.post("/db/query", json={}, headers=alice).status_code == 422
    assert client.post("/db/query", json={"sql": "select 1", "x": 1}, headers=alice).status_code == 422
    assert sql(client, alice, "SELECT 1\x00").status_code == 400
    with pytest.raises(sqlbox.DbError):
        sqlbox.run_query(db_path(1), "SELECT '" + "a" * 10000 + "'")


def test_browse_table_with_paging_and_search(client, alice):
    seed(client, alice)
    page = client.get("/db/tables/people", params={"page": 1, "pageSize": 2}, headers=alice).json()
    assert page == {"columns": ["id", "name", "note"], "rows": [[1, "An", "x"], [2, "Bình", "100%"]], "total": 3, "page": 1, "pageSize": 2}
    second = client.get("/db/tables/people", params={"page": 2, "pageSize": 2}, headers=alice).json()
    assert second["rows"] == [[3, "Chi", "a_b"]]
    found = client.get("/db/tables/people", params={"q": "bình"}, headers=alice).json()
    assert found["total"] == 1 and found["rows"][0][1] == "Bình"
    assert client.get("/db/tables/people", params={"q": "%"}, headers=alice).json()["total"] == 1  # '%' is literal
    assert client.get("/db/tables/people", params={"q": "_"}, headers=alice).json()["total"] == 1
    assert client.get("/db/tables/people", params={"q": "zzz"}, headers=alice).json()["total"] == 0
    assert client.get("/db/tables/people", params={"q": "' OR 1=1 --"}, headers=alice).json()["total"] == 0


def test_browse_validates_name_and_limits(client, alice):
    seed(client, alice)
    for name in ("people;DROP TABLE people", 'people" --', "sqlite_master", "nope", "%2e%2e", "PEOPLE2"):
        assert client.get(f"/db/tables/{name}", headers=alice).status_code == 404
    assert client.get("/db/tables/people", params={"pageSize": 201}, headers=alice).status_code == 422
    assert client.get("/db/tables/people", params={"pageSize": 0}, headers=alice).status_code == 422
    assert client.get("/db/tables/people", params={"page": 0}, headers=alice).status_code == 422
    assert client.get("/db/tables/people", params={"q": "x" * 201}, headers=alice).status_code == 422
    assert client.get("/db/tables/" + "a" * 65, headers=alice).status_code == 422
    assert sql(client, alice, "SELECT count(*) FROM people").json()["rows"] == [[3]]


def test_browse_odd_table_and_column_names(client, alice):
    sql(client, alice, 'CREATE TABLE "we ird""t" ("a b" TEXT, "c""d" TEXT)')
    sql(client, alice, "INSERT INTO \"we ird\"\"t\" VALUES ('v1', 'v2')")
    body = client.get('/db/tables/we ird"t', params={"q": "v2"}, headers=alice).json()
    assert body["columns"] == ["a b", 'c"d'] and body["total"] == 1
    export = client.get("/db/export", params={"table": 'we ird"t'}, headers=alice)
    assert export.status_code == 200 and 'filename="we_ird_t.csv"' in export.headers["content-disposition"]


def test_browse_table_without_columns_matches_nothing(client, alice, monkeypatch):
    seed(client, alice)
    sql(client, alice, "CREATE VIEW v AS SELECT 1")
    assert client.get("/db/tables/v", headers=alice).status_code == 404  # views are not tables


def test_import_creates_text_columns(client, alice):
    r = upload_csv(client, alice, "name,age\nAn,30\nBình,25\n", table="people2")
    assert r.status_code == 201 and r.json() == {"table": "people2", "rows": 2}
    info = sql(client, alice, "PRAGMA table_info(people2)").json()["rows"]
    assert [(row[1], row[2]) for row in info] == [("name", "TEXT"), ("age", "TEXT")]
    assert client.get("/db/tables", headers=alice).json() == [{"name": "people2", "rows": 2}]


def test_import_short_rows_bom_and_quotes(client, alice):
    r = upload_csv(client, alice, b"\xef\xbb\xbfa,b,c\r\n1,\"x,y\"\r\n\r\n\"q\"\"q\",2,3\r\n", table="t")
    assert r.status_code == 201 and r.json()["rows"] == 2
    rows = sql(client, alice, "SELECT * FROM t").json()["rows"]
    assert rows == [["1", "x,y", ""], ['q"q', "2", "3"]]


@pytest.mark.parametrize(
    "csv_text,table,status",
    [
        ("", "t", 400),
        (",\n1,2\n", "t", 400),
        ("a,a\n1,2\n", "t", 400),
        ("a,A\n1,2\n", "t", 400),
        ("a,b\n1,2,3\n", "t", 400),
        ("a\x01b,c\n1,2\n", "t", 400),
        ("a,b\n1,2\n", "1bad", 400),
        ("a,b\n1,2\n", "bad name", 400),
        ("a,b\n1,2\n", 'x"y', 400),
        ("a,b\n1,2\n", "sqlite_x", 400),
        ("a,b\n1,2\n", "t" * 65, 400),
        ("a\n1\x00\n", "t", 400),
        (",".join(f"c{i}" for i in range(51)) + "\n", "t", 400),
        ("x" * 65 + ",b\n1,2\n", "t", 400),
        ('"unterminated,b\n1,2\n', "t", 400),
    ],
)
def test_import_rejects(client, alice, csv_text, table, status):
    assert upload_csv(client, alice, csv_text, table=table).status_code == status
    assert client.get("/db/tables", headers=alice).json() == []


def test_import_limits(client, alice):
    fifty = ",".join(f"c{i}" for i in range(50))
    assert upload_csv(client, alice, fifty + "\n", table="wide").status_code == 201
    rows = "a\n" + "1\n" * 20000
    assert upload_csv(client, alice, rows, table="many").json()["rows"] == 20000
    assert upload_csv(client, alice, "a\n" + "1\n" * 20001, table="toomany").status_code == 413
    assert upload_csv(client, alice, b"a\n" + b"x" * (2 * 1024 * 1024), table="big").status_code == 413
    assert upload_csv(client, alice, b"a\n\xff\xfe\n", table="latin").status_code == 400
    names = [row["name"] for row in client.get("/db/tables", headers=alice).json()]
    assert names == ["many", "wide"]


def test_import_declared_length_and_missing_fields(client, alice):
    headers = {**alice, "Content-Type": "multipart/form-data; boundary=x"}
    assert client.post("/db/import", content=iter([b"--x--"]), headers=headers).status_code == 411
    assert client.post("/db/import", content=b"x", headers={**headers, "Content-Length": str(3 * 1024 * 1024)}).status_code == 413
    assert client.post("/db/import", data={"table": "t"}, headers=alice).status_code == 422


def test_import_existing_table_and_table_count(client, alice, monkeypatch):
    assert upload_csv(client, alice, "a\n1\n", table="t").status_code == 201
    assert upload_csv(client, alice, "a\n1\n", table="t").status_code == 409
    monkeypatch.setattr(sqlbox, "MAX_TABLES", 1)
    assert upload_csv(client, alice, "a\n1\n", table="u").status_code == 409


def test_import_into_full_database(client, alice, monkeypatch):
    monkeypatch.setattr(sqlbox, "MAX_DB_BYTES", 16 * 4096)
    big = "a\n" + ("z" * 3000 + "\n") * 100
    r = upload_csv(client, alice, big, table="t")
    assert r.status_code == 413 and "20 MB" in r.json()["detail"]
    assert client.get("/db/tables", headers=alice).json() == []


def test_export_csv_with_formula_guard(client, alice):
    sql(client, alice, "CREATE TABLE f (a TEXT, \"=HYPERLINK(1)\" TEXT, n INTEGER)")
    sql(client, alice, "INSERT INTO f VALUES ('=1+1', '+cmd', -5), ('@SUM(A1)', '-2', 7), ('ok', 'a,b', NULL), ('\tx', 'y', 1)")
    r = client.get("/db/export", params={"table": "f"}, headers=alice)
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment") and r.headers["content-disposition"].endswith('f.csv"')
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode())))
    assert rows[0] == ["a", "'=HYPERLINK(1)", "n"]
    assert rows[1] == ["'=1+1", "'+cmd", "-5"]  # numbers are not text: untouched
    assert rows[2] == ["'@SUM(A1)", "'-2", "7"]
    assert rows[3] == ["ok", "a,b", ""]
    assert rows[4][0] == "'\tx"


def test_export_errors(client, alice):
    sql(client, alice, "CREATE TABLE f (a)")
    assert client.get("/db/export", params={"table": "nope"}, headers=alice).status_code == 404
    assert client.get("/db/export", headers=alice).status_code == 422
    assert client.get("/db/export", params={"table": "sqlite_master"}, headers=alice).status_code == 404


def test_delete_database(client, alice):
    seed(client, alice)
    assert db_path(1).exists()
    assert client.delete("/db", headers=alice).status_code == 204
    assert not db_path(1).exists()
    assert client.delete("/db", headers=alice).status_code == 204  # idempotent
    assert client.get("/db/tables", headers=alice).json() == []


def test_users_have_separate_databases(client, alice, bob):
    seed(client, alice)
    assert client.get("/db/tables", headers=bob).json() == []
    assert client.get("/db/tables/people", headers=bob).status_code == 404
    assert sql(client, bob, "SELECT * FROM people").status_code == 400
    assert client.get("/db/export", params={"table": "people"}, headers=bob).status_code == 404
    sql(client, bob, "CREATE TABLE people (only_bob TEXT)")
    assert client.get("/db/tables/people", headers=alice).json()["columns"] == ["id", "name", "note"]
    client.delete("/db", headers=bob)
    assert client.get("/db/tables", headers=alice).json() == [{"name": "people", "rows": 3}]
    # another database file cannot be reached by name
    for target in ("2", "../2", "2.sqlite3"):
        r = sql(client, alice, f"ATTACH DATABASE '{target}' AS other")
        assert r.status_code == 400


def test_origin_and_rate_limits(client, alice):
    evil = {**alice, "Origin": "https://evil.example"}
    assert client.post("/db/query", json={"sql": "select 1"}, headers=evil).status_code == 403
    assert client.delete("/db", headers=evil).status_code == 403
    assert client.post("/db/import", data={"table": "t"}, files={"file": ("a.csv", b"a\n1", "text/csv")}, headers=evil).status_code == 403
    codes = [sql(client, alice, "SELECT 1").status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429
    assert sql(client, auth_cookie(3, "cy"), "SELECT 1").status_code == 200


def test_read_rate_limit(client, alice):
    client.app.state.read_limiter = type(client.app.state.limiter)(max_events=2)
    assert [client.get("/db/tables", headers=alice).status_code for _ in range(3)] == [200, 200, 429]


def test_busy_user_gets_429(client, alice, monkeypatch):
    from app import store

    monkeypatch.setattr(store, "LOCK_TIMEOUT_SECONDS", 0.05)
    lock = store._locks[1 % store.LOCK_STRIPES]
    original = store.user_lock.__init__

    def short(self, user_id, timeout=0.05):
        original(self, user_id, timeout)

    monkeypatch.setattr(store.user_lock, "__init__", short)
    with lock:
        assert client.get("/db/tables", headers=alice).status_code == 429
        assert sql(client, alice, "select 1").status_code == 429
        assert client.post("/files/folder", json={"path": "/", "name": "a"}, headers=alice).status_code == 429


def test_unexpected_open_failure_is_a_clean_500_message(monkeypatch, tmp_path):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file " + str(tmp_path))

    monkeypatch.setattr(sqlbox.sqlite3, "connect", broken)
    with pytest.raises(sqlbox.DbError) as caught:
        sqlbox.run_query(tmp_path / "x.sqlite3", "select 1")
    assert caught.value.status == 500 and str(tmp_path) not in caught.value.detail


def test_cell_helper_handles_bool_and_text():
    assert sqlbox.cell(True) is True
    assert sqlbox.cell("x") == "x"
    assert sqlbox.guard_formula(5) == 5 and sqlbox.guard_formula("plain") == "plain"
