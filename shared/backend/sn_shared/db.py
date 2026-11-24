"""Database engine and session dependency shared by every backend (each app keeps its own `Base` and models)."""

from typing import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    if url in ("sqlite://", "sqlite:///:memory:"):
        # One shared connection so every thread sees the same in-memory database.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, connect_args={"check_same_thread": False})


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def rename_table(engine: Engine, old: str, new: str) -> None:
    """Rename a table kept from before its name changed: only when the old one is there and the new one is not."""
    tables = set(inspect(engine).get_table_names())
    if old in tables and new not in tables:
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {old} RENAME TO {new}"))


def ensure_columns(engine: Engine, table: str, columns: dict[str, str]) -> None:
    """Add the columns a table still lacks (`create_all` makes tables but never alters them).

    `columns` maps a column name to its SQL definition, e.g. {"status": "VARCHAR(16) NOT NULL DEFAULT 'ready'"}.
    Only for additive changes: nothing is dropped or retyped.
    """
    existing = {column["name"] for column in inspect(engine).get_columns(table)}
    with engine.begin() as connection:
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def retire_columns(engine: Engine, legacy: dict[str, list[str]]) -> list[str]:
    """Columns the code no longer has, left in a database that was made before: they must not refuse the new rows.

    PostgreSQL (the platform): the column is only allowed to be empty (it is dropped by hand, when it suits). SQLite
    (development): the column is dropped, with the indexes that hold it. Tables and columns that are not there are skipped.
    Returns the `table.column` names that were changed.
    """
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
