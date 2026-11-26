"""Idempotent schema upgrade for the `users` table (no migration framework in this repo).

`Base.metadata.create_all` creates missing tables but never alters existing ones, so
databases created before the auth upgrade get their new columns added here.
Portable to SQLite and PostgreSQL.
"""

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Engine, Integer, LargeBinary, String, Text, inspect, text
from sqlalchemy.types import TypeEngine
from sn_shared.db import add_column_sql

TABLE = "users"
NEW_CODES = "verification_codes"

# (name, type, NOT NULL default literal by dialect family or None for nullable)
_COLUMNS: tuple[tuple[str, TypeEngine, tuple[str, str] | None], ...] = (
    ("email", String(254), None),
    ("google_sub", String(64), None),
    ("group", String(16), ("'user'", "'user'")),
    ("kind", String(8), ("'human'", "'human'")),
    ("token_version", Integer(), ("0", "0")),
    ("audio_embedding", LargeBinary(), None),
    ("face_embedding", LargeBinary(), None),
    ("voice_login", Boolean(), ("0", "FALSE")),
    ("webcam_login", Boolean(), ("0", "FALSE")),
    ("biometric_2fa", Boolean(), ("0", "FALSE")),
    ("email_verified", Boolean(), ("0", "FALSE")),
    ("email_from_google", Boolean(), ("0", "FALSE")),
    ("phone", String(16), None),
    ("phone_verified", Boolean(), ("0", "FALSE")),
    ("totp_enabled", Boolean(), ("0", "FALSE")),
    ("totp_secret", Text(), None),
    ("totp_pending_secret", Text(), None),
    ("totp_last_step", BigInteger(), None),
    ("username_changed_at", DateTime(timezone=True), None),
    ("name", String(100), None),
    ("address", String(255), None),
    ("headline", String(120), None),
    ("summary", Text(), None),
    ("birth_date", Date(), None),
    ("city", String(80), None),
    ("region", String(80), None),
    ("country", String(80), None),
    ("avatar_url", String(255), None),
    ("interests", JSON(), None),
    ("persona_role", String(200), None),
    ("speaking_style", String(200), None),
    ("links", JSON(), None),
    ("experience", JSON(), None),
    ("education", JSON(), None),
    ("skills", JSON(), None),
    ("languages", JSON(), None),
    ("certifications", JSON(), None),
    ("projects", JSON(), None),
    ("visibility", JSON(), None),
)
UNIQUE_INDEXES = (("uq_users_email", "email"), ("uq_users_google_sub", "google_sub"), ("uq_users_phone", "phone"),
                   ("uq_users_username_lower", "lower(username)"))  # case-insensitive identity (replaced users.username_key)


def column_ddl(engine: Engine, name: str, type_: TypeEngine, default: tuple[str, str] | None) -> str:
    literal = None if default is None else (default[1] if engine.dialect.name == "postgresql" else default[0])
    return add_column_sql(engine, TABLE, name, type_, literal)


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
                conn.execute(text(column_ddl(engine, name, type_, default)))
                added.append(name)
        if "group" in added and "role" in existing:
            # users.role became users.group: copy the values once, then drop the old column.
            conn.execute(text(f'UPDATE {TABLE} SET "group" = role'))
            conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN role"))
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
        if "username_key" in existing:
            # Legacy column: PostgreSQL keeps it (dropped by hand later) but new rows, which no longer set it, must be allowed;
            # a SQLite (development) database loses it with its unique index.
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"ALTER TABLE {TABLE} ALTER COLUMN username_key DROP NOT NULL"))
            else:
                conn.execute(text("DROP INDEX IF EXISTS uq_users_username_key"))
                conn.execute(text(f"ALTER TABLE {TABLE} DROP COLUMN username_key"))
        for index_name, column in UNIQUE_INDEXES:
            conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {TABLE} ({column})"))
    merge_legacy_codes(engine)
    return added


def merge_legacy_codes(engine: Engine) -> int:
    """Copy `email_tokens` and `phone_codes` into `verification_codes`, only while that table is empty.

    The old tables stay (dropped by hand). Email rows keep their ids, because a code MAC is bound to the row id, so
    pending codes and links still work; phone rows get fresh ids and no code (their MAC cannot be re-bound, and a
    code lives 10 minutes anyway). Returns the number of rows copied.
    """
    tables = set(inspect(engine).get_table_names())
    if NEW_CODES not in tables:
        return 0
    copied = 0
    with engine.begin() as conn:
        if conn.execute(text(f"SELECT 1 FROM {NEW_CODES} LIMIT 1")).first() is not None:
            return 0
        if "email_tokens" in tables:
            copied += conn.execute(text(
                f"INSERT INTO {NEW_CODES} (id, user_id, purpose, channel, target, token_hash, code_hash, attempts, expires_at, used_at) "
                "SELECT id, user_id, purpose, 'email', email, token_hash, code_hash, attempts, expires_at, used_at FROM email_tokens"
            )).rowcount
            if engine.dialect.name == "postgresql":  # explicit ids do not advance the sequence
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{NEW_CODES}', 'id'), COALESCE((SELECT MAX(id) FROM {NEW_CODES}), 1))"
                ))
        if "phone_codes" in tables:
            copied += conn.execute(text(
                f"INSERT INTO {NEW_CODES} (user_id, purpose, channel, target, token_hash, code_hash, attempts, expires_at, used_at) "
                "SELECT user_id, purpose, 'phone', phone, NULL, NULL, attempts, expires_at, used_at FROM phone_codes"
            )).rowcount
    return copied
