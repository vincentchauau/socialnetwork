"""Virtual people: accounts made by the platform, not by a person (the pool the chat draws companions from).

A virtual person is a row of `users` with `kind = "virtual"`: one table means one namespace of names (nobody can take a name a
virtual person has, nor the other way round) and one kind of id for every service. The other apps read them there (see
`sn_shared.directory`): nothing is announced to them and no copy is kept. It has no password (`NO_PASSWORD`), no
e-mail, no phone and no biometrics, and nothing signs it in: `issue_session` refuses any account that is not `human`, and it is
the end of every sign-in and refresh. Its words are written by the agent service, never by a browser.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.center.handles import key_of
from api.center.models import User
from api.center.passwords import NO_PASSWORD

import logging
logger = logging.getLogger(__name__)

VIRTUAL = "virtual"


class NameTaken(Exception):
    """The name is already used (by a person or by a virtual one)."""


def create_virtual(db: Session, username: str, **profile: object) -> User:
    """A virtual person with this name and profile (the caller commits). Raises NameTaken when the name is used."""
    try:
        if db.scalar(select(User.id).where(func.lower(User.username) == key_of(username))) is not None:
            raise NameTaken(username)
        user = User(username=username, password_hash=NO_PASSWORD, kind=VIRTUAL, **profile)
        db.add(user)
        db.flush()
        return user
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_virtual failed")
        raise
