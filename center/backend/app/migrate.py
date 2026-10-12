"""Idempotent schema upgrade for the `users` table (no migration framework in this repo).

`Base.metadata.create_all` creates missing tables but never alters existing ones, so
databases created before the auth upgrade get their new columns added here.
Portable to SQLite and PostgreSQL.
"""

from sqlalchemy import BigInteger, Boolean, Engine, Integer, LargeBinary, String, Text, inspect, text
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
    ("voice_login", Boolean(), ("0", "FALSE")),
    ("webcam_login", Boolean(), ("0", "FALSE")),
    ("biometric_2fa", Boolean(), ("0", "FALSE")),
    ("email_verified", Boolean(), ("0", "FALSE")),
    ("email_from_google", Boolean(), ("0", "FALSE")),
    ("totp_enabled", Boolean(), ("0", "FALSE")),
    ("totp_secret", Text(), None),
    ("totp_pending_secret", Text(), None),
    ("totp_last_step", BigInteger(), None),
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


def sessions_table_is_new(engine: Engine) -> bool:
    """True when `users` exists but `user_sessions` does not yet (call BEFORE create_all): the first start of
    the release that introduced sessions, whose old tokens carry no sid and could never be revoked."""
    tables = set(inspect(engine).get_table_names())
    return TABLE in tables and "user_sessions" not in tables


def force_relogin(engine: Engine) -> None:
    """One-time: bump every token_version so every pre-sessions token dies (a single forced re-login)."""
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET token_version = token_version + 1"))


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
        if "webcam_login" in added and "biometric_login" in {*existing, *added}:
            # Old passwordless mode needed face + voice = the webcam method. Runs once, when the column
            # is created: re-running it later would resurrect a webcam login the user switched off.
            true = "TRUE" if engine.dialect.name == "postgresql" else "1"
            conn.execute(
                text(f"UPDATE {TABLE} SET webcam_login = {true} WHERE biometric_login AND NOT webcam_login")
            )
        if "email_verified" in added:
            # Google verified those addresses itself. Runs once, when the column is created: re-running it
            # would re-verify an address the user later replaced or removed.
            true = "TRUE" if engine.dialect.name == "postgresql" else "1"
            conn.execute(
                text(f"UPDATE {TABLE} SET email_verified = {true} WHERE google_sub IS NOT NULL AND email IS NOT NULL")
            )
        if "email_from_google" in added:
            # Before this column, a Google account's address was assumed to come from Google. Runs once, when
            # the column is created: re-running it would re-flag an address the user verified themselves.
            true = "TRUE" if engine.dialect.name == "postgresql" else "1"
            conn.execute(
                text(f"UPDATE {TABLE} SET email_from_google = {true} WHERE google_sub IS NOT NULL AND email IS NOT NULL")
            )
        for index_name, column in _UNIQUE_INDEXES:
            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {TABLE} ({column})"))
    return added
