"""The pool of virtual people: a fixed list of names, so running the seed again (or on another server) gives the same people.

The account and the whole profile (age, place, interests, role and way of speaking: see `virtual_profiles`) live in `users`; the
chat and the agent read them there.
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.center.handles import is_valid_username, key_of
from api.center.models import User
from api.center.usernames import unavailable
from api.center.virtual import create_virtual
from api.center.virtual_profiles import SEED, profile_for

import logging
logger = logging.getLogger(__name__)

POOL_SIZE = 300

GIVEN = (
    "An", "Anh", "Binh", "Chi", "Cuong", "Dung", "Duy", "Giang", "Ha", "Hai", "Hanh", "Hien", "Hieu", "Hoa", "Hung", "Huong",
    "Khanh", "Khoa", "Lam", "Lan", "Linh", "Long", "Mai", "Minh", "Nam", "Ngan", "Nga", "Nhung", "Phong", "Phuc", "Phuong",
    "Quan", "Quang", "Quynh", "Son", "Tam", "Thao", "Thanh", "Thu", "Trang", "Trung", "Tuan", "Tuyet", "Vinh", "Vy", "Yen",
)
FAMILY = ("Nguyen", "Tran", "Le", "Pham", "Hoang", "Huynh", "Vu", "Dang", "Bui", "Do", "Ngo", "Duong", "Ly", "Phan", "Truong")


def candidate_names(size: int = POOL_SIZE) -> list[str]:
    """The first `size` names of a fixed shuffle of every given+family pair ("Lan_Nguyen"); the same list on every run."""
    try:
        pairs = sorted(f"{given}_{family}" for given in GIVEN for family in FAMILY)
        random.Random(SEED).shuffle(pairs)
        return pairs[:size]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("candidate_names failed")
        raise


def seed_pool(db: Session, size: int = POOL_SIZE) -> int:
    """Create the missing people of the pool and return how many were added (0 when it is already complete). Caller commits."""
    try:
        existing = {key_of(name) for name in db.scalars(select(User.username).where(User.kind == "virtual"))}
        added = 0
        for name in candidate_names(size):
            if key_of(name) in existing or not is_valid_username(name) or unavailable(db, name):
                continue  # already there, or a person took the name first: the pool simply has one fewer
            create_virtual(db, name, **profile_for(name))
            added += 1
        return added
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("seed_pool failed")
        raise
