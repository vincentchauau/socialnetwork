"""Skills: one vocabulary for what a person knows, what a job asks for and what a course teaches.

A skill is a name that people write in many ways ("Python", " python ", "Node.js", "nodejs"): `skill_key` makes one key of them, so a
job that asks for "NodeJS" and a person who knows "node.js" meet. The catalog is one table, `skills` (key, name as first written): what the suggestions are drawn from. Each job keeps its own
skills in its row (`skills_required`, `skills_preferred`, and their keys in `skill_keys`).

The levels and the years stay with the thing that states them (the profile of a person, the description of a job); `match` compares
what a job asks with what a person has and gives the score.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Engine, String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from sn_shared.db import get_db
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)

NAME_MAX = 60
LEVELS = {"beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
REQUIRED_WEIGHT = 0.8  # of the score: what is asked; the rest is what is only liked
PARTIAL_CREDIT = 0.5  # for a skill that is there, at a lower level or for fewer years than asked

# Other ways to write the same skill.
ALIASES = {
    "js": "javascript", "ecmascript": "javascript", "ts": "typescript", "py": "python", "golang": "go", "reactjs": "react", "react.js": "react",
    "node": "node.js", "nodejs": "node.js", "vuejs": "vue", "vue.js": "vue", "postgres": "postgresql", "k8s": "kubernetes", "ml": "machine learning",
    "c sharp": "c#", "csharp": "c#", "cpp": "c++", "dotnet": ".net", "aws": "amazon web services",
}


class Base(DeclarativeBase):
    pass


class Skill(Base):
    __tablename__ = "skills"

    key: Mapped[str] = mapped_column(String(NAME_MAX), primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX))  # as it was first written




def ensure_tables(engine: Engine) -> None:
    try:
        Base.metadata.create_all(engine)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_tables failed")
        raise


def skill_key(name: str) -> str:
    """One key for the many ways to write a skill: no case, no accents, one space between words, the usual short names spelled out."""
    try:
        plain = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
        folded = "".join(c for c in plain if not unicodedata.combining(c)).casefold()
        words = re.sub(r"\s+", " ", folded).strip(" ,;")
        return ALIASES.get(words, words)[:NAME_MAX]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("skill_key failed")
        raise


def keys_of(names: Iterable[str]) -> list[str]:
    """The keys of these names, once each, sorted (what a job row keeps to be found by skill)."""
    try:
        return sorted({skill_key(name) for name in names if name and name.strip()})
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("keys_of failed")
        raise


def distinct(names: Iterable[str]) -> dict[str, str]:
    """key -> the first spelling, for the names that are not empty."""
    try:
        found: dict[str, str] = {}
        for name in names:
            key = skill_key(name)
            if key and key not in found:
                found[key] = name.strip()[:NAME_MAX]
        return found
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("distinct failed")
        raise


# ---- the catalog and the links --------------------------------------------------------------------------------------


def register(db: Session, names: Iterable[str]) -> list[str]:
    """Add the skills to the catalog (one that is there stays as it is); returns their keys. The caller commits."""
    try:
        found = distinct(names)
        if not found:
            return []
        known = set(db.scalars(select(Skill.key).where(Skill.key.in_(list(found)))))
        db.add_all(Skill(key=key, name=name) for key, name in found.items() if key not in known)
        return list(found)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("register failed")
        raise


def names_of(db: Session, keys: Iterable[str]) -> dict[str, str]:
    """key -> the name to show."""
    try:
        keys = list(dict.fromkeys(keys))
        if not keys:
            return {}
        return {skill.key: skill.name for skill in db.scalars(select(Skill).where(Skill.key.in_(keys)))}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("names_of failed")
        raise


def suggest(db: Session, words: str, limit: int = 10) -> "list[SkillOut]":
    """The skills of the catalog that start like these words; with no words, the first in order of key."""
    try:
        query = select(Skill.key, Skill.name)
        if words.strip():
            query = query.where(Skill.key.startswith(skill_key(words), autoescape=True))
        rows = db.execute(query.order_by(Skill.key).limit(limit)).all()
        return [SkillOut(key=row.key, name=row.name) for row in rows]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("suggest failed")
        raise


# ---- how well a person fits a job ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    """`score` is 0..100, or None when the job asks for no skills (there is nothing to compare)."""

    score: int | None
    matched: list[str] = field(default_factory=list)  # asked for, and the person has it (as much as asked)
    partial: list[str] = field(default_factory=list)  # asked for, and the person has it at a lower level or for fewer years
    missing: list[str] = field(default_factory=list)  # asked for, and the person lacks it
    missing_preferred: list[str] = field(default_factory=list)  # only liked, and the person lacks it


def credit_skills(wanted: Mapping[str, Any], have: Mapping[str, Mapping[str, Any]]) -> float:
    """1 for a skill that is there as asked, PARTIAL_CREDIT when it is there below the level or the years asked, 0 when it is not."""
    try:
        mine = have.get(skill_key(str(wanted.get("name") or "")))
        if mine is None:
            return 0.0
        level_wanted, level_mine = LEVELS.get(wanted.get("level") or "", 0), LEVELS.get(mine.get("level") or "", 0)
        years_wanted, years_mine = wanted.get("years") or 0, mine.get("years") or 0
        below = (level_wanted and level_mine and level_mine < level_wanted) or (years_wanted and mine.get("years") is not None and years_mine < years_wanted)
        return PARTIAL_CREDIT if below else 1.0
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("credit_skills failed")
        raise


def match(required: Iterable[Mapping[str, Any]], preferred: Iterable[Mapping[str, Any]], have: Iterable[Mapping[str, Any]]) -> Match:
    """What a job asks (`required`, and `preferred` which only counts for a fifth), each as {name, level, years}, against what a person
    has: how many of the asked skills they have, as much as asked."""
    try:
        people = {skill_key(str(item.get("name") or "")): item for item in have if skill_key(str(item.get("name") or ""))}
        wanted_required = [item for item in required if skill_key(str(item.get("name") or ""))]
        wanted_preferred = [item for item in preferred if skill_key(str(item.get("name") or ""))]
        if not wanted_required and not wanted_preferred:
            return Match(score=None)
        matched, partial, missing, missing_preferred = [], [], [], []
        required_total = 0.0
        for item in wanted_required:
            credit = credit_skills(item, people)
            required_total += credit
            (matched if credit == 1.0 else partial if credit else missing).append(str(item["name"]).strip())
        preferred_total = 0.0
        for item in wanted_preferred:
            credit = credit_skills(item, people)
            preferred_total += credit
            if not credit:
                missing_preferred.append(str(item["name"]).strip())
        required_ratio = required_total / len(wanted_required) if wanted_required else None
        preferred_ratio = preferred_total / len(wanted_preferred) if wanted_preferred else None
        if required_ratio is None:
            ratio = preferred_ratio or 0.0
        elif preferred_ratio is None:
            ratio = required_ratio
        else:
            ratio = REQUIRED_WEIGHT * required_ratio + (1 - REQUIRED_WEIGHT) * preferred_ratio
        return Match(score=round(ratio * 100), matched=matched, partial=partial, missing=missing, missing_preferred=missing_preferred)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("match failed")
        raise


# ---- the suggestions over HTTP ------------------------------------------------------------------------------------------


class SkillOut(BaseModel):
    key: str
    name: str


def skills_router() -> APIRouter:
    """`GET /skills?q=py`: the skills of the catalog that start like the words, for the field that asks for a skill."""
    try:
        router = APIRouter(tags=["skills"])

        @router.get("/skills", response_model=list[SkillOut])
        def suggestions(
            _user: Annotated[TokenPayload, Depends(get_current_user)],
            db: Annotated[Session, Depends(get_db)],
            q: Annotated[str, Query(max_length=NAME_MAX)] = "",
            limit: Annotated[int, Query(ge=1, le=50)] = 10,
        ) -> list[SkillOut]:
            try:
                return suggest(db, q, limit)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("suggestions failed")
                raise

        return router
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("skills_router failed")
        raise


def total(db: Session) -> int:
    try:
        return db.scalar(select(func.count()).select_from(Skill)) or 0
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("total failed")
        raise
