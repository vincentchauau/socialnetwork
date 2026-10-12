"""Reactions to account events published by `center` (delivered at least once).

Data model: `game_players` (user_id, username) inside `game_results`. Results
are shared history that the other players still see, so on deletion the rows
are KEPT and ANONYMIZED: `user_id` becomes the tombstone 0 (center ids start
at 1) and `username` becomes DELETED_USERNAME. Rename updates every
`game_players.username` of that user id.

In-memory rooms (`RoomStore`) are NOT touched: a handler only receives a DB
session and the store lives on the app instance, so there is no safe handle to
it. A deleted user's token stops working, so the room is reaped by the normal
idle timeout (30 minutes) and its result then carries the stored name.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import GamePlayer

DELETED_USERNAME = "Người dùng đã xóa"
DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(
        update(GamePlayer)
        .where(GamePlayer.user_id == user_id)
        .values(user_id=DELETED_USER_ID, username=DELETED_USERNAME)
    )


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(update(GamePlayer).where(GamePlayer.user_id == user_id).values(username=new_username))
