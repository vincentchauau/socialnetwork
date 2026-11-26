"""The account `system`: the voice of the platform in the places where words are kept (the lines of a chat room that say who came or was sent away).

It is a row of `users` like any other, with a fixed id (-1: no person ever has it, the ids of people count up from 1) and `kind = "system"`:
one table means one namespace of names (nobody can register as `system`), and the services know it by id and name without asking center.
It has no password (`NO_PASSWORD`) and nothing signs it in: `issue_session` refuses any account that is not `human`. No event announces it:
the other apps do not keep a profile for it.
"""

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.center.handles import key_of
from api.center.models import User
from api.center.passwords import NO_PASSWORD

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = -1
SYSTEM_USERNAME = "system"
SYSTEM_KIND = "system"

log = logging.getLogger(__name__)


def ensure_system_user(db: Session) -> User | None:
    """Make the account `system` when it is not there (safe to repeat); None when a person took the name first. Commits."""
    try:
        found = db.get(User, SYSTEM_USER_ID)
        if found is not None:
            return found
        taken = db.query(User).filter(func.lower(User.username) == key_of(SYSTEM_USERNAME)).first()
        if taken is not None:
            log.warning("the name %r is taken by user %s: the chat says its lines under that id instead", SYSTEM_USERNAME, taken.id)
            return None
        user = User(id=SYSTEM_USER_ID, username=SYSTEM_USERNAME, password_hash=NO_PASSWORD, kind=SYSTEM_KIND)
        db.add(user)
        db.commit()
        return user
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_system_user failed")
        raise
