from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, Session
from sn_shared.db import make_engine  # noqa: F401  (center's cli and main import it from here)

import logging
logger = logging.getLogger(__name__)


DEFAULT_DATABASE_URL = "sqlite:///./center.db"


class Base(DeclarativeBase):
    pass


def get_db(request: Request) -> Iterator[Session]:
    try:
        with request.app.state.session_factory() as session:
            yield session
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_db failed")
        raise
