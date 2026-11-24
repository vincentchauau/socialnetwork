"""The people the demo data belongs to: read from `users`, handed out in a fixed order."""

import random
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from sn_shared.directory import Person
from sn_shared.skills import skill_key

ADMIN_ID = 1  # the human administrator


@dataclass(frozen=True)
class PersonInfo:
    id: int
    username: str
    kind: str
    headline: str
    summary: str
    skills: tuple[dict, ...]  # {name, level, years}
    keys: frozenset[str]  # skill keys of the profile

    @property
    def name(self) -> str:
        return self.username.replace("_", " ")


def load_people(db: Session) -> list[PersonInfo]:
    """Every real person (id above 0, not the platform account), by id."""
    rows = db.scalars(select(Person).where(Person.user_id > 0, Person.kind != "system").order_by(Person.user_id))
    people = []
    for row in rows:
        items = tuple(i for i in (row.skills or []) if isinstance(i, dict) and isinstance(i.get("name"), str))
        people.append(PersonInfo(
            id=row.user_id, username=row.username, kind=row.kind or "human", headline=(row.headline or "").strip(),
            summary=(row.summary or "").strip(), skills=items, keys=frozenset(skill_key(i["name"]) for i in items),
        ))
    return people


def keys_of(names) -> frozenset[str]:
    return frozenset(skill_key(name) for name in names)


class Cast:
    """Hands out virtual people (the admin only when asked): people not used yet come first, and a person whose profile has the
    wanted skills comes before one that has none, so a person who knows Python teaches the Python course."""

    def __init__(self, people: list[PersonInfo], rng: random.Random) -> None:
        self.admin = next((p for p in people if p.id == ADMIN_ID), None)
        self.humans = [p for p in people if p.kind == "human"]
        self.virtual = [p for p in people if p.kind == "virtual"]
        rng.shuffle(self.virtual)
        self._used: set[int] = set()
        self.by_id = {p.id: p for p in people}

    def take(self, wanted: frozenset[str] = frozenset(), exclude=()) -> PersonInfo:
        pool = [p for p in self.virtual if p.id not in exclude]
        if not pool:
            pool = [p for p in [self.admin, *self.humans] if p is not None and p.id not in exclude]
        if not pool:
            raise LookupError("not enough people")
        fresh = [p for p in pool if p.id not in self._used] or pool
        chosen = next((p for p in fresh if p.keys & wanted), fresh[0])
        self._used.add(chosen.id)
        return chosen

    def admin_or_take(self, wanted: frozenset[str] = frozenset(), exclude=()) -> PersonInfo:
        if self.admin is not None and self.admin.id not in exclude:
            return self.admin
        return self.take(wanted, exclude)
