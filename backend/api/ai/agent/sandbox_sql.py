"""db_tool's database: a throwaway SQLite snapshot of the user's own data, read with a locked-down SELECT.

AppCity's db_tool took a connection string and ran any SQL on it. Here the model never sees the real database: for each
call a small in-memory SQLite database is built from rows the person may see (the tables are the ones an app's scope names), and the query runs on that copy, so there is
nothing to change, nothing of anyone else's to read, and nothing left behind. On top of that:

- one statement that begins with SELECT or WITH, nothing else;
- SQLite's authorizer allows reading and plain functions only (no write, no ATTACH, no PRAGMA, no extension);
- a step budget stops a runaway query, and a row cap and a text cap bound the answer.
"""

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

import logging
logger = logging.getLogger(__name__)

ROW_LIMIT_DEFAULT = 20
ROW_LIMIT_MAX = 100
QUERY_MAX = 1000
CELL_CHARS = 300
STEP_BUDGET = 2_000_000  # SQLite VM instructions, checked every 1000
ALLOWED_FUNCTIONS = {
    "abs", "avg", "count", "date", "datetime", "julianday", "strftime", "length", "lower", "upper", "max", "min", "round",
    "sum", "total", "substr", "trim", "ltrim", "rtrim", "replace", "instr", "coalesce", "ifnull", "nullif", "typeof",
    "group_concat", "like", "glob", "printf", "cast", "iif", "time", "unixepoch",
}

class QueryError(ValueError):
    """The query is not one this tool runs, or it failed; the message goes back to the model."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


def describe(schema: dict[str, str]) -> str:
    """The tables the model may query (`{name: "column TYPE, ..."}`), for its description of the tool."""
    try:
        return "; ".join(f"{name}({columns})" for name, columns in schema.items())
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("describe failed")
        raise


def authorizer_sandbox_sql(action: int, arg1: str | None, arg2: str | None, db: str | None, source: str | None) -> int:
    try:
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("authorizer_sandbox_sql failed")
        raise


def check_query(query: str) -> str:
    try:
        text = query.strip().rstrip(";").strip()
        if not text:
            raise QueryError("The query is empty")
        if len(text) > QUERY_MAX:
            raise QueryError(f"The query is longer than {QUERY_MAX} characters")
        if ";" in text:
            raise QueryError("Only one statement is allowed")
        if not re.match(r"(?is)^(select|with)\b", text):
            raise QueryError("Only SELECT queries are allowed")
        return text
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("check_query failed")
        raise


def run_query(tables: dict[str, list[tuple]], query: str, limit: int, schema: dict[str, str]) -> QueryResult:
    """Build the snapshot from `tables` (name -> rows, in the column order of `schema`) and run `query` on it."""
    text = check_query(query)
    connection = sqlite3.connect(":memory:")
    try:
        for name, columns in schema.items():
            connection.execute(f"CREATE TABLE {name} ({columns})")
            rows = tables.get(name, [])
            if rows:
                marks = ",".join("?" * len(rows[0]))
                connection.executemany(f"INSERT INTO {name} VALUES ({marks})", rows)
        connection.commit()
        connection.set_authorizer(authorizer_sandbox_sql)
        steps = {"n": 0}

        def budget() -> int:
            try:
                steps["n"] += 1000
                return 1 if steps["n"] > STEP_BUDGET else 0
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("budget failed")
                raise

        connection.set_progress_handler(budget, 1000)
        try:
            cursor = connection.execute(text)
            names = [column[0] for column in cursor.description or []]
            fetched = cursor.fetchmany(limit + 1)
        except sqlite3.Error as error:
            raise QueryError(f"The query failed: {str(error)[:200]}") from None
        shown = [[cell(value) for value in row] for row in fetched[:limit]]
        return QueryResult(columns=names, rows=shown, truncated=len(fetched) > limit)
    finally:
        connection.close()


def cell(value: Any) -> Any:
    try:
        if isinstance(value, str):
            return value[:CELL_CHARS]
        if isinstance(value, bytes):
            return "<binary>"
        return value
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("cell failed")
        raise
