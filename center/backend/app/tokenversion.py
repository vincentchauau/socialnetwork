"""Revoking sessions: `token_version` is bumped by the database, never by a read-modify-write in Python."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app import usersessions
from app.audit import audit
from app.config import Settings
from app.models import User
from sn_shared import revocation


def access_ttl_seconds(settings: Settings) -> int:
    """How long a revocation key must live: the longest access token plus a minute of slack."""
    return settings.access_minutes * 60 + usersessions.REVOCATION_SLACK_SECONDS


def bump_token_version(db: Session, user: User, keep_sid: str | None = None) -> None:
    """`UPDATE users SET token_version = token_version + 1` (atomic, so two concurrent bumps are two bumps).

    Every session row of the user is marked revoked too, except `keep_sid` (the caller re-issues that session).
    The caller commits, THEN calls `publish_token_version`. The instance is refreshed (that column only) so
    cookies issued afterwards carry the new value.
    """
    db.flush()  # pending changes on the instance (e.g. a new password hash) are written, not discarded
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(token_version=User.token_version + 1)
        .execution_options(synchronize_session=False)
    )
    usersessions.revoke_all_of(db, user.id, keep_sid)
    db.refresh(user, ["token_version"])


def publish_token_version(user: User, settings: Settings) -> bool:
    """Tell the other apps the account's minimum token version (best effort: see sn_shared.revocation)."""
    ok = revocation.publish_min_version(user.id, user.token_version, access_ttl_seconds(settings))
    if not ok and revocation.configured():
        audit.warning("minimum token version not published (1 account): other apps may accept its tokens until expiry")
    return ok
