"""Revoking sessions: `token_version` is bumped by the database, never by a read-modify-write in Python."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from api.center import usersessions
from api.center.audit import audit
from api.center.config import Settings
from api.center.models import User
from sn_shared import revocation

import logging
logger = logging.getLogger(__name__)


def access_ttl_seconds(settings: Settings) -> int:
    """How long a revocation key must live: the longest access token plus a minute of slack."""
    try:
        return settings.access_minutes * 60 + usersessions.REVOCATION_SLACK_SECONDS
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("access_ttl_seconds failed")
        raise


def bump_token_version(db: Session, user: User, keep_sid: str | None = None) -> None:
    """`UPDATE users SET token_version = token_version + 1` (atomic, so two concurrent bumps are two bumps).

    Every session row of the user is marked revoked too, except `keep_sid` (the caller re-issues that session).
    The caller commits, THEN calls `publish_token_version`. The instance is refreshed (that column only) so
    cookies issued afterwards carry the new value.
    """
    try:
        db.flush()  # pending changes on the instance (e.g. a new password hash) are written, not discarded
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(token_version=User.token_version + 1)
            .execution_options(synchronize_session=False)
        )
        usersessions.revoke_all_of(db, user.id, keep_sid)
        db.refresh(user, ["token_version"])
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("bump_token_version failed")
        raise


def publish_token_version(user: User | int, settings: Settings, version: int | None = None) -> bool:
    """Tell the other apps the account's minimum token version (best effort: see sn_shared.revocation).

    Takes a User, or a user id plus `version` (the user row may already be deleted)."""
    try:
        user_id, version = (user.id, user.token_version) if isinstance(user, User) else (user, version)
        ok = revocation.publish_min_version(user_id, version, access_ttl_seconds(settings))
        if not ok and revocation.configured():
            audit.warning("minimum token version not published (1 account): other apps may accept its tokens until expiry")
        return ok
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("publish_token_version failed")
        raise
