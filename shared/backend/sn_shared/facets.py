"""The counts behind a filter tree (the categories of the market, the tags of the courses, the types of the jobs)."""

from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


class Facet(BaseModel):
    name: str
    count: int


def facets(db: Session, column, rows: Select, *, limit: int = 30) -> list[Facet]:
    """The most used values of `column` among `rows` (a select of the rows that count), the most used first, then by name."""
    counted = rows.with_only_columns(column.label("name"), func.count().label("n")).group_by(column).subquery()
    found = db.execute(select(counted.c.name, counted.c.n).where(counted.c.name != "").order_by(counted.c.n.desc(), counted.c.name).limit(limit))
    return [Facet(name=name, count=n) for name, n in found]
