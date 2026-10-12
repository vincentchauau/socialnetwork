"""Revoking sessions: `token_version` is bumped by the database, never by a read-modify-write in Python."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import User


def bump_token_version(db: Session, user: User) -> None:
    """`UPDATE users SET token_version = token_version + 1` (atomic, so two concurrent bumps are two bumps).

    The caller commits. The instance is refreshed (that column only) so cookies issued afterwards carry the new value.
    """
    db.flush()  # pending changes on the instance (e.g. a new password hash) are written, not discarded
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
        .execution_options(synchronize_session=False)
    )
    db.refresh(user, ["token_version"])
