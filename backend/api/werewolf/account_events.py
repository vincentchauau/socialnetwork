"""Reactions to account events published by `center` (delivered at least once).

Data model: a finished game (`games`, status `finished`) holds its HUMAN players as a list (`players`, and `player_ids` to find the games
of one person). Only humans are stored (a bot seat has no user), so every entry there is a user. The other fields hold no personal data.
Results are shared history that the other players still see, so on deletion the games are KEPT and ANONYMIZED: `user_id` becomes the
tombstone 0 (center ids start at 1), which the directory names DELETED_USERNAME. Rename does nothing: no name is stored.

In-memory rooms (`RoomStore`) are NOT touched: a handler only receives a DB session and the store lives on the app instance, so there is
no safe handle to it. A deleted user's token stops working, so the room is reaped by the normal idle timeout (30 minutes).

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.werewolf.models import FINISHED, Game, ids_text

DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id <= DELETED_USER_ID:  # the tombstone, or a bogus id: never a real user
        return
    for game in db.scalars(select(Game).where(Game.status == FINISHED, Game.player_ids.like(f"%|{int(user_id)}|%"))):
        # (a new list: an edited one is not seen as changed)
        game.players = [{**p, "user_id": DELETED_USER_ID} if p.get("user_id") == user_id else p for p in game.players]
        game.player_ids = ids_text(p["user_id"] for p in game.players)


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """Nothing to do: a game keeps only the user ids; the name is read from center's `users` when the history is served."""
