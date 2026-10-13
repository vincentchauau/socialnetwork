"""Idempotent schema upgrade for the result tables (no migration framework in this repo).

`Base.metadata.create_all` creates missing tables but never alters existing ones, so databases created by the old
4-role game get the new columns added here (same approach as center/backend/app/migrate.py). Portable to SQLite
and PostgreSQL; old rows keep working because every new column has a default.
"""

from sqlalchemy import Engine, Integer, String, inspect, text
from sqlalchemy.types import TypeEngine

# table -> (name, type, NOT NULL default literal)
_COLUMNS: dict[str, tuple[tuple[str, TypeEngine, str], ...]] = {
    "game_results": (("size", Integer(), "0"),),
    "game_players": (
        ("faction", String(16), "''"),
        ("ability", String(24), "''"),
        ("outcome", String(8), "''"),
        ("days_survived", Integer(), "0"),
    ),
}


def _column_ddl(engine: Engine, table: str, name: str, type_: TypeEngine, default: str) -> str:
    ddl = f"ALTER TABLE {table} ADD COLUMN "
    if engine.dialect.name == "postgresql":
        ddl += "IF NOT EXISTS "  # safe when several workers start together
    return ddl + f"{name} {type_.compile(dialect=engine.dialect)} NOT NULL DEFAULT {default}"


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
                    conn.execute(text(_column_ddl(engine, table, name, type_, default)))
                    added.append(f"{table}.{name}")
    return added
