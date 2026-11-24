"""Admin CRUD over every table of center (mounted at /admin in main.py).

All tables hold credentials or account state, so all are read + delete only. Deleting goes through the same
paths the app uses, so other modules and sessions stay consistent:
- `users`: the same steps as DELETE /auth/me (USER_DELETED outbox event and username reservation in one
  transaction, token_version bump that revokes every session, then publish to the other apps and the relay).
  An admin cannot delete their own account here.
- `user_sessions`: the row is deleted and its sid is published to the cross-app revocation store.
"""

from typing import Callable

from fastapi import HTTPException, Request, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.center import usernames
from api.center.audit import audit
from api.center.events import USER_DELETED, add_event
from api.center.models import (
    AccountEvent,
    Passkey,
    QrLogin,
    RecoveryCode,
    ReservedUsername,
    User,
    UserSession,
    VerificationCode,
)
from api.center.tokenversion import access_ttl_seconds, bump_token_version, publish_token_version
from sn_shared import revocation
from sn_shared.admincrud import TableSpec, records_router
from sn_shared.security import TokenPayload

SELF_DELETE = "You cannot delete your own account here"


def delete_user(request: Request, db: Session, row, admin: TokenPayload) -> Callable[[], None]:
    """The account-deletion path of DELETE /auth/me, without the re-authentication and cookies."""
    user_id = row["id"]
    if user_id == admin.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, SELF_DELETE)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    username = user.username
    add_event(db, USER_DELETED, user_id, {"old_username": username})  # same transaction as the delete
    usernames.reserve(db, username, user_id)
    bump_token_version(db, user)
    min_version = user.token_version
    db.delete(user)
    settings = request.app.state.settings
    relay = request.app.state.event_relay

    def after_commit() -> None:
        publish_token_version(user_id, settings, min_version)
        relay.publish_pending()
        audit.info("account deleted by admin user=%r admin_id=%s", username, admin.user_id)

    return after_commit


def delete_user_session(request: Request, db: Session, row, admin: TokenPayload) -> Callable[[], None]:
    """Delete the row and publish its sid as revoked, so the other apps reject its access token at once."""
    sid = row["sid"]
    db.execute(delete(UserSession).where(UserSession.sid == sid))
    ttl = access_ttl_seconds(request.app.state.settings)
    return lambda: revocation.publish_session_revoked(sid, ttl)


# What a person may see of their own account at /data/users: the public profile, nothing credential-like or internal.
USER_VISIBLE_COLUMNS = frozenset({
    "id", "username", "email", "name", "headline", "summary", "city", "region", "country", "avatar_url", "birth_date",
    "skills", "experience", "education", "languages", "interests", "links", "certifications", "projects", "visibility",
})  # fmt: skip
USER_HIDDEN_COLUMNS = tuple(c.name for c in User.__table__.columns if c.name not in USER_VISIBLE_COLUMNS)


def specs() -> list[TableSpec]:
    """Admin tables, plus the /data twin for a signed-in person: users (own row, read), user_sessions and passkeys
    (own rows, read + delete). The other tables have no owner, so people do not reach them."""
    ro = "RD"
    return [
        TableSpec(
            User, media={"avatar_url": {"kind": "image", "preview": "@self"}}, on_delete=delete_user, user_hidden_columns=USER_HIDDEN_COLUMNS,
            secret_columns=(
                "password_hash", "totp_secret", "totp_pending_secret", "totp_last_step",
                "audio_embedding", "face_embedding",
            ),
        ),
        TableSpec(UserSession, on_delete=delete_user_session, owner="user_id", groups=("admin",)),
        TableSpec(
            Passkey, secret_columns=("credential_id", "public_key", "user_handle"), owner="user_id", groups=("admin",)
        ),
        TableSpec(RecoveryCode, secret_columns=("code_hash",)),
        TableSpec(VerificationCode, secret_columns=("token_hash", "code_hash")),
        TableSpec(QrLogin, secret_columns=("poll_hash", "verify_code")),
        TableSpec(ReservedUsername),
        TableSpec(AccountEvent),
    ]


def records():
    return records_router(specs(), database="center")
