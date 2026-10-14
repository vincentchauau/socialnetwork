from typing import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    if url in ("sqlite://", "sqlite:///:memory:"):
        # One shared connection so every thread sees the same in-memory database.
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(url, connect_args={"check_same_thread": False})


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
