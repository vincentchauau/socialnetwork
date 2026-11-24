from sqlalchemy.orm import DeclarativeBase

from sn_shared.db import get_db, make_engine

__all__ = ["Base", "get_db", "make_engine"]


class Base(DeclarativeBase):
    pass
