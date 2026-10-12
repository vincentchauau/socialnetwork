"""Idempotent schema upgrade for the `users` table (no migration framework in this repo).

`Base.metadata.create_all` creates missing tables but never alters existing ones, so
databases created before the auth upgrade get their new columns added here.
Portable to SQLite and PostgreSQL.
"""

from sqlalchemy import Boolean, Engine, Integer, LargeBinary, String, inspect, text
from sqlalchemy.types import TypeEngine

TABLE = "users"

# (name, type, NOT NULL default literal by dialect family or None for nullable)
_COLUMNS: tuple[tuple[str, TypeEngine, tuple[str, str] | None], ...] = (
    ("email", String(254), None),
    ("google_sub", String(64), None),
    ("role", String(16), ("'user'", "'user'")),
    ("token_version", Integer(), ("0", "0")),
    ("audio_embedding", LargeBinary(), None),
    ("face_embedding", LargeBinary(), None),
    ("biometric_login", Boolean(), ("0", "FALSE")),
    ("biometric_2fa", Boolean(), ("0", "FALSE")),
)
_UNIQUE_INDEXES = (("uq_users_email", "email"), ("uq_users_google_sub", "google_sub"))


def _column_ddl(engine: Engine, name: str, type_: TypeEngine, default: tuple[str, str] | None) -> str:
    sql_type = type_.compile(dialect=engine.dialect)
    ddl = f"ALTER TABLE {TABLE} ADD COLUMN "
    if engine.dialect.name == "postgresql":
        ddl += "IF NOT EXISTS "  # safe when several workers start together
    ddl += f"{name} {sql_type}"
    if default is not None:
        literal = default[1] if engine.dialect.name == "postgresql" else default[0]
        ddl += f" NOT NULL DEFAULT {literal}"
    return ddl


def ensure_columns(engine: Engine) -> list[str]:
    """Add missing columns/indexes to `users`; returns the names of added columns."""
    if TABLE not in inspect(engine).get_table_names():
        return []
    existing = {column["name"] for column in inspect(engine).get_columns(TABLE)}
    added: list[str] = []
    with engine.begin() as conn:
        for name, type_, default in _COLUMNS:
            if name not in existing:
                conn.execute(text(_column_ddl(engine, name, type_, default)))
                added.append(name)
        for index_name, column in _UNIQUE_INDEXES:
            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {TABLE} ({column})"))
    return added
