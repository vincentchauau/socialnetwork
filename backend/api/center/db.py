from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, Session
from sn_shared.db import make_engine  # noqa: F401  (center's cli and main import it from here)


DEFAULT_DATABASE_URL = "sqlite:///./center.db"


class Base(DeclarativeBase):
    pass


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
