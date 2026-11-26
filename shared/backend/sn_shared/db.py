"""Database engine and session dependency shared by every backend (each app keeps its own `Base` and models)."""

from typing import Iterator

from fastapi import Request
from sqlalchemy.types import TypeEngine
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import logging
logger = logging.getLogger(__name__)


def make_engine(url: str) -> Engine:
    try:
        if not url.startswith("sqlite"):
            return create_engine(url, pool_pre_ping=True)
        if url in ("sqlite://", "sqlite:///:memory:"):
            # One shared connection so every thread sees the same in-memory database.
            return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
        return create_engine(url, connect_args={"check_same_thread": False})
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("make_engine failed")
        raise


def get_db(request: Request) -> Iterator[Session]:
    try:
        with request.app.state.session_factory() as session:
            yield session
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_db failed")
        raise


def rename_table(engine: Engine, old: str, new: str) -> None:
    """Rename a table kept from before its name changed: only when the old one is there and the new one is not."""
    try:
        tables = set(inspect(engine).get_table_names())
        if old in tables and new not in tables:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {old} RENAME TO {new}"))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("rename_table failed")
        raise


def ensure_foreign_key(engine: Engine, table: str, column: str, ref_table: str, ref_column: str = "id") -> None:
    """Add the foreign key the model declares, when the table was made before it (create_all only makes new tables).

    The same rule as the model: nothing is deleted by it (no cascade); the code deletes the rows that refer to a row before it.
    Only adds the key when no key already covers the column.
    """
    try:
        if engine.dialect.name != "postgresql":  # sqlite (tests) cannot add a key to a table; its tables get the keys when made
            return
        inspector = inspect(engine)
        if table not in inspector.get_table_names() or ref_table not in inspector.get_table_names():
            return
        if any(column in fk["constrained_columns"] and fk["referred_table"] == ref_table for fk in inspector.get_foreign_keys(table)):
            return
        name = f"fk_{table}_{column}"
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}) REFERENCES {ref_table} ({ref_column})"))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_foreign_key failed")
        raise


def add_column_sql(engine: Engine, table: str, name: str, type_: TypeEngine, default: str | None = None) -> str:
    """The ALTER TABLE that adds one column to an existing table. On PostgreSQL it is `IF NOT EXISTS` (safe when
    several workers start together); `default` is the SQL literal of the default, when the column has one."""
    try:
        ddl = f"ALTER TABLE {table} ADD COLUMN "
        if engine.dialect.name == "postgresql":
            ddl += "IF NOT EXISTS "
        ddl += f'"{name}" {type_.compile(dialect=engine.dialect)}'
        if default is not None:
            ddl += f" NOT NULL DEFAULT {default}"
        return ddl
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("add_column_sql failed")
        raise


def ensure_columns(engine: Engine, table: str, columns: dict[str, str]) -> None:
    """Add the columns a table still lacks (`create_all` makes tables but never alters them).

    `columns` maps a column name to its SQL definition, e.g. {"status": "VARCHAR(16) NOT NULL DEFAULT 'ready'"}.
    Only for additive changes: nothing is dropped or retyped.
    """
    try:
        existing = {column["name"] for column in inspect(engine).get_columns(table)}
        with engine.begin() as connection:
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_columns failed")
        raise


def retire_columns(engine: Engine, legacy: dict[str, list[str]]) -> list[str]:
    """Columns the code no longer has, left in a database that was made before: they must not refuse the new rows.

    PostgreSQL (the platform): the column is only allowed to be empty (it is dropped by hand, when it suits). SQLite
    (development): the column is dropped, with the indexes that hold it. Tables and columns that are not there are skipped.
    Returns the `table.column` names that were changed.
    """
    try:
        done: list[str] = []
        tables = set(inspect(engine).get_table_names())
        with engine.begin() as connection:
            for table, columns in legacy.items():
                if table not in tables:
                    continue
                for column in columns:
                    info = {c["name"]: c for c in inspect(connection).get_columns(table)}
                    if column not in info:
                        continue
                    if engine.dialect.name == "postgresql":
                        if info[column].get("nullable"):
                            continue
                        connection.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP NOT NULL'))
                    else:
                        for index in inspect(connection).get_indexes(table):
                            if column in index["column_names"]:
                                connection.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
                        connection.execute(text(f'ALTER TABLE "{table}" DROP COLUMN "{column}"'))
                    done.append(f"{table}.{column}")
        return done
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("retire_columns failed")
        raise
