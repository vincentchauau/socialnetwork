"""Searching text without minding case or accents: "nha" finds "Nhà", "dong" finds "Đồng".

The text is folded the same way on both sides: in Python (`fold`) for what is looked for and for the lines that say where it
was found, and in the database (`fold_text`) for the column it is looked for in. PostgreSQL gets `fold_text` from its
`unaccent` extension, with a trigram index on messages so `LIKE '%…%'` does not read them all; SQLite (the tests) gets a
Python function. A database that cannot do it (no right to make the extension) falls back to plain `lower()`: the search
still works, only without folding the accents there (`folded` says which one is in use).
"""

import logging
import unicodedata

from sqlalchemy import Engine, event, func, text
from sqlalchemy.sql.elements import ColumnElement

log = logging.getLogger(__name__)

DB_FOLDS = {"on": False}  # set once at start: does the database have `fold_text`?


def fold(value: str) -> str:
    """Lower case, without accents (`đ` is `d`)."""
    plain = unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in plain if not unicodedata.combining(c)).lower()


def folded(column: ColumnElement) -> ColumnElement:
    """The column as the search sees it: folded in the database when it can, else only lower-cased."""
    return func.fold_text(column) if DB_FOLDS["on"] else func.lower(column)


def pattern(words: str) -> str:
    """`%words%` for a LIKE (escape `\\`), folded, the words taken literally: a % or _ typed is not a wildcard."""
    escaped = fold(words.strip()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def register_sqlite(engine: Engine) -> None:
    """Give SQLite the `fold_text` function (a connection made later has it too)."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _add(connection, _record) -> None:  # noqa: ANN001 - the DBAPI connection
        connection.create_function("fold_text", 1, lambda value: None if value is None else fold(value), deterministic=True)

    DB_FOLDS["on"] = True


POSTGRES_SETUP = (
    "CREATE EXTENSION IF NOT EXISTS unaccent",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    # unaccent() is not marked immutable, which an index needs: this wrapper says it is (its rules never change). Everything
    # is named with its schema: PostgreSQL 17 builds an index with a search path that holds nothing but pg_catalog.
    "CREATE OR REPLACE FUNCTION public.immutable_unaccent(text) RETURNS text AS "
    "$$ SELECT public.unaccent('public.unaccent', $1) $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT",
    "CREATE OR REPLACE FUNCTION public.fold_text(text) RETURNS text AS "
    "$$ SELECT lower(public.immutable_unaccent(replace(replace($1, 'đ', 'd'), 'Đ', 'D'))) $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT",
    "CREATE INDEX IF NOT EXISTS ix_messages_content_fold ON messages USING gin (public.fold_text(content) public.gin_trgm_ops)",
)


def ensure_postgres(engine: Engine) -> bool:
    """Make `fold_text` and the index on PostgreSQL; False (and the plain search) when the database does not allow it."""
    if engine.dialect.name != "postgresql":
        return False
    try:
        with engine.begin() as connection:
            for statement in POSTGRES_SETUP:
                connection.execute(text(statement))
    except Exception:  # noqa: BLE001 - any refusal of the database means: search without folding there
        log.warning("accent-insensitive search is off: the database refused unaccent/pg_trgm", exc_info=True)
        return False
    DB_FOLDS["on"] = True
    return True
