from sn_shared.db import get_db, make_engine
from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base", "get_db", "make_engine"]


class Base(DeclarativeBase):
    pass
