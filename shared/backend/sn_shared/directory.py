"""The people of the platform, read from `users` of center: the only place where a person is kept.

An app that needs to know who somebody is (a name, a headline, a picture, how a virtual person speaks) reads it here, instead of
keeping a copy that has to be kept up to date. This module only reads: a person is made, changed and deleted by center.

What a person shows is what they chose to show (`visibility` of the profile: a part is seen by everybody only when it is `public`);
a virtual person, made by the platform, shows all of it. The username is always seen. `view` says what a viewer may read.
"""

from datetime import date
from typing import NamedTuple

from collections.abc import Iterable

from sqlalchemy import JSON, Date, Engine, Integer, String, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import logging
logger = logging.getLogger(__name__)

SUMMARY_MAX = 500  # how much of the summary is shown (the profile of an account holds more)
PUBLIC = "public"
DELETED_USERNAME = "Người dùng đã xóa"  # who a row of a person that is gone is said to belong to


class Base(DeclarativeBase):
    """Only to read `users`: this metadata is never used to make tables of the platform (center makes `users`)."""


class PersonView(NamedTuple):
    """A person as a viewer may read them."""

    display_name: str
    headline: str
    region: str
    avatar: str
    summary: str  # what is written: whether the viewer may read it is `summary_public` (or being a friend)
    summary_public: bool
    birth_year: int | None
    interests: list[str]


class Person(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column("id", Integer, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(8), default="human")  # human | virtual (made by the platform)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    interests: Mapped[list | None] = mapped_column(JSON, nullable=True)
    persona_role: Mapped[str | None] = mapped_column(String(200), nullable=True)  # a virtual person: who they are in a story
    speaking_style: Mapped[str | None] = mapped_column(String(200), nullable=True)  # and how they speak
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)  # {name, level, years}
    visibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @property
    def is_virtual(self) -> bool:
        try:
            return self.kind == "virtual"
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("is_virtual failed")
            raise

    @property
    def place(self) -> str:
        """Where they are: the region, or else the city."""
        try:
            return (self.region or self.city or "").strip()
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("place failed")
            raise

    def skill_items(self, own: bool = False) -> list[dict]:
        """The skills of the profile as {name, level, years}: all of them to the person themselves, else only when the profile shows them."""
        try:
            if not (own or self.shows("skills")):
                return []
            return [item for item in (self.skills or []) if isinstance(item, dict) and isinstance(item.get("name"), str)]
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("skill_items failed")
            raise

    def shows(self, part: str) -> bool:
        """Does everybody see this part of the profile? (A virtual person shows all of it.)"""
        try:
            return self.is_virtual or (self.visibility or {}).get(part) == PUBLIC
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("shows failed")
            raise

    def view(self, own: bool = False) -> PersonView:
        """What a viewer may read; `own` is the person looking at themselves, who reads everything."""
        try:
            def seen(part: str, value: str | None) -> str:
                try:
                    return (value or "").strip() if own or self.shows(part) else ""
                except Exception as error:
                    if getattr(error, "status_code", None) is None:
                        logger.exception("seen failed")
                    raise

            if self.is_virtual:
                display_name = (self.name or "").strip() or self.username.replace("_", " ")
            else:
                display_name = seen("name", self.name)
            return PersonView(
                display_name=display_name,
                headline=seen("headline", self.headline),
                region=seen("location", self.place),
                avatar=seen("avatar", self.avatar_url),
                summary=(self.summary or "").strip()[:SUMMARY_MAX],
                summary_public=self.shows("summary"),
                birth_year=self.birth_date.year if self.is_virtual and self.birth_date else None,
                interests=[item for item in (self.interests or []) if isinstance(item, str)] if self.is_virtual else [],
            )
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("view failed")
            raise


def names(db: Session, user_ids: Iterable[int]) -> dict[int, str]:
    """The username of each person: rows keep only `user_id`, the name is read here, so a rename shows everywhere at once.
    A person who is gone (deleted, or the negative id left by an anonymized row) has the name of nobody."""
    try:
        user_ids = list(user_ids)
        wanted = {int(user_id) for user_id in user_ids if user_id is not None and user_id > 0}
        found = dict(db.execute(select(Person.user_id, Person.username).where(Person.user_id.in_(wanted))).all()) if wanted else {}
        return {int(user_id): found.get(int(user_id), DELETED_USERNAME) for user_id in user_ids if user_id is not None}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("names failed")
        raise


def name_of(db: Session, user_id: int | None) -> str:
    try:
        return "" if user_id is None else names(db, [user_id])[user_id]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("name_of failed")
        raise


def attach_names(db: Session, rows: Iterable, id_attr: str = "user_id", name_attr: str = "username") -> list:
    """Puts the username on each row (a plain attribute, not a column) so that a schema can read it from the row."""
    try:
        rows = list(rows)
        found = names(db, [getattr(row, id_attr) for row in rows])
        for row in rows:
            setattr(row, name_attr, found[getattr(row, id_attr)] if getattr(row, id_attr) is not None else "")
        return rows
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("attach_names failed")
        raise


def ensure_table_for_sqlite(engine: Engine) -> None:
    """A SQLite database (development, tests) has no center beside it: an empty `users` is made so that the queries still run.
    In PostgreSQL the table is center's and is never touched here."""
    try:
        if engine.dialect.name == "sqlite":
            Base.metadata.create_all(engine)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_table_for_sqlite failed")
        raise
