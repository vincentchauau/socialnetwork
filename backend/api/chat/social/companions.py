"""Companions: virtual people a person drew at random from the pool to be with (a private chat, a room, a game).

The pool is shared and the draw is at random; what is private is the pair (who drew whom). A companion is `acquainted`: the
private chat with them opens at once, because a virtual person cannot answer a request.
"""

import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from sn_shared.directory import Person

from api.chat.social import service
from api.chat.social.models import COMPANION, Edge

import logging
logger = logging.getLogger(__name__)

MAX_COMPANIONS = 300  # active ones per person: the size of the pool
MAX_PER_DRAW = 100


def active_ids(db: Session, owner_id: int) -> set[int]:
    try:
        return set(db.scalars(select(Edge.dst_id).where(Edge.kind == COMPANION, Edge.src_id == owner_id, Edge.released_at.is_(None))))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("active_ids failed")
        raise


def is_companion(db: Session, owner_id: int, other_id: int) -> bool:
    try:
        row = db.get(Edge, (owner_id, other_id, COMPANION))
        return row is not None and row.released_at is None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("is_companion failed")
        raise


def draw(db: Session, owner_id: int, count: int, region: str = "", interest: str = "", rng: random.Random | None = None, exclude: set[int] | None = None) -> list[Person]:
    """`count` virtual people at random, none of them already a companion or blocked, narrowed by place or interest when asked.
    Fewer come back when the pool (or the room left under the limit) is short. Caller commits."""
    try:
        mine = active_ids(db, owner_id)
        room_left = MAX_COMPANIONS - len(mine)
        if room_left <= 0:
            raise service.Refused(409, "You already have as many companions as allowed")
        query = select(Person).where(Person.kind == "virtual", Person.user_id.not_in(mine | service.blocked_ids(db, owner_id) | {owner_id} | (exclude or set())))
        pool = list(db.scalars(query))
        if region.strip():  # compared here, not in SQL: lower() of a database does not fold every letter (Đ)
            pool = [person for person in pool if person.place.casefold() == region.strip().casefold()]
        if interest.strip():
            wanted = interest.strip().casefold()
            pool = [person for person in pool if wanted in (item.casefold() for item in person.interests or [])]
        chosen = (rng or random.SystemRandom()).sample(pool, min(count, MAX_PER_DRAW, room_left, len(pool)))
        for person in chosen:
            row = db.get(Edge, (owner_id, person.user_id, COMPANION))
            if row is None:
                db.add(Edge(src_id=owner_id, dst_id=person.user_id, kind=COMPANION))
            else:
                row.released_at = None  # drawn again
        return chosen
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("draw failed")
        raise


def pick(db: Session, owner_id: int, count: int, exclude: set[int] | None = None, rng: random.Random | None = None) -> list[Person]:
    """`count` virtual people at random who are not `exclude`d, nor blocked by or against `owner_id`: for a room that needs people (they do not
    become companions: the limit of companions is for the ones a person chose). Fewer come back when the pool is short."""
    try:
        skip = (exclude or set()) | service.blocked_ids(db, owner_id) | {owner_id}
        pool = list(db.scalars(select(Person).where(Person.kind == "virtual", Person.user_id.not_in(skip))))
        return (rng or random.SystemRandom()).sample(pool, min(max(count, 0), len(pool)))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("pick failed")
        raise


def release(db: Session, owner_id: int, virtual_id: int) -> None:
    try:
        row = db.get(Edge, (owner_id, virtual_id, COMPANION))
        if row is not None and row.released_at is None:
            row.released_at = datetime.now(timezone.utc)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("release failed")
        raise
