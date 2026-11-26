"""Idempotent schema upgrade for the result tables (no migration framework in this repo).

`Base.metadata.create_all` creates missing tables but never alters existing ones, so databases created by the old
4-role game get the new columns added here (same approach as center/backend/app/migrate.py). Portable to SQLite
and PostgreSQL; old rows keep working because every new column has a default.
"""

from datetime import datetime, timezone

from sn_shared.db import add_column_sql
from sqlalchemy import Engine, Integer, String, inspect, text
from sqlalchemy.types import TypeEngine

from api.werewolf.models import FINISHED, LIVE, Game, ids_text
from api.werewolf.rolecode import role_code

# table -> (name, type, NOT NULL default literal)
_COLUMNS: dict[str, tuple[tuple[str, TypeEngine, str], ...]] = {
    "game_results": (("size", Integer(), "0"),),
    "game_players": (
        ("outcome", String(8), "''"),
        ("days_survived", Integer(), "0"),
    ),
}


def ensure_columns(engine: Engine) -> list[str]:
    """Add the missing columns of existing tables; returns the added `table.column` names."""
    tables = set(inspect(engine).get_table_names())
    added: list[str] = []
    with engine.begin() as conn:
        for table, columns in _COLUMNS.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspect(engine).get_columns(table)}
            for name, type_, default in columns:
                if name not in existing:
                    conn.execute(text(add_column_sql(engine, table, name, type_, default)))
                    added.append(f"{table}.{name}")
        fold_role_columns(conn, tables)
        drop_stored_username(conn, tables)
    return added


def drop_stored_username(conn, tables: set[str]) -> None:
    """`game_players.username` is gone (the name is read from center's `users`): until the live column is dropped by hand
    it must not refuse new rows; a SQLite (development) database simply loses the column."""
    if "game_players" not in tables or "username" not in {c["name"] for c in inspect(conn).get_columns("game_players")}:
        return
    if conn.dialect.name == "postgresql":
        conn.execute(text("ALTER TABLE game_players ALTER COLUMN username DROP NOT NULL"))
    else:
        conn.execute(text("ALTER TABLE game_players DROP COLUMN username"))


def fold_role_columns(conn, tables: set[str]) -> None:
    """Rows written while `faction` and `ability` were columns kept the faction alone in `role`: put both into the role
    code, so those two columns (dropped by hand) carry nothing that is lost. Idempotent: only rows without a code."""
    if "game_players" not in tables:
        return
    columns = {column["name"] for column in inspect(conn).get_columns("game_players")}
    if not {"faction", "ability"} <= columns:
        return
    fold_rows(conn)
    for name in ("faction", "ability"):  # folded: new rows do not set them, so they must be allowed (SQLite: they go)
        if conn.dialect.name == "postgresql":
            conn.execute(text(f"ALTER TABLE game_players ALTER COLUMN {name} DROP NOT NULL"))
        else:
            conn.execute(text(f"ALTER TABLE game_players DROP COLUMN {name}"))


def fold_rows(conn) -> None:
    rows = conn.execute(text("SELECT id, faction, ability FROM game_players "
                             "WHERE outcome <> '' AND faction <> '' AND ability <> '' AND role NOT LIKE '%:%'")).all()
    for row_id, faction, ability in rows:
        try:
            code = role_code(faction, ability)
        except KeyError:
            continue
        conn.execute(text("UPDATE game_players SET role = :role WHERE id = :id"), {"role": code, "id": row_id})


def read_all(conn, table: str, wanted: tuple[str, ...]) -> list[dict]:
    """The rows of an old table, with the columns it has among `wanted` (an older database lacks some)."""
    if table not in set(inspect(conn).get_table_names()):
        return []
    have = {column["name"] for column in inspect(conn).get_columns(table)}
    columns = [name for name in wanted if name in have]
    return [dict(row) for row in conn.execute(text(f"SELECT {', '.join(columns)} FROM {table} ORDER BY 1")).mappings()]


def merge_legacy_tables(engine: Engine) -> int:
    """The three tables of before (`game_results`, `game_players`, `ww_snapshots`) are one now (`games`): copy their rows, once.

    Runs only while `games` is empty, so a second start (or a database that has been used since) copies nothing. The old tables are
    left where they are: drop them by hand when the copy has been looked at. Returns how many rows were copied.
    """
    if "games" not in set(inspect(engine).get_table_names()):
        return 0
    with engine.begin() as conn:
        if conn.execute(text("SELECT COUNT(*) FROM games")).scalar():
            return 0
        results = read_all(conn, "game_results", ("id", "room_id", "winner", "days", "size", "finished_at"))
        players = read_all(conn, "game_players", ("result_id", "user_id", "role", "outcome", "survived", "days_survived", "id"))
        snapshots = read_all(conn, "ww_snapshots", ("code", "data"))
        of_game: dict[int, list[dict]] = {}
        for p in sorted(players, key=lambda row: row.get("id", 0)):
            of_game.setdefault(p["result_id"], []).append({
                "user_id": p["user_id"], "role": p.get("role", ""), "outcome": p.get("outcome", ""),
                "survived": bool(p.get("survived")), "days_survived": p.get("days_survived", 0),
            })
        finished = [
            {
                "room_code": r["room_id"], "status": FINISHED, "winner": r["winner"], "days": r["days"], "size": r.get("size", 0) or 0,
                "finished_at": _aware(r.get("finished_at")),
                "players": of_game.get(r["id"], []), "player_ids": ids_text(p["user_id"] for p in of_game.get(r["id"], [])),
            }
            for r in results
        ]
        live = [
            {"room_code": s["code"], "status": LIVE, "state": s["data"], "players": [], "player_ids": ""}
            for s in snapshots
        ]
        for rows in (finished, live):  # (one statement for each kind: the rows of a statement have the same columns)
            if rows:
                conn.execute(Game.__table__.insert(), rows)
    return len(finished) + len(live)


def _aware(value) -> datetime | None:
    """A moment read back as text (SQLite) or as a datetime, with its time zone."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value
