from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, LargeBinary, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from api.werewolf.db import Base
from sn_shared.clock import utcnow  # noqa: F401  (re-exported: history.py takes it from here)

import logging
logger = logging.getLogger(__name__)

LIVE = "live"  # the saved room of a game that is on (or waiting for a rematch): put back when the server starts again
FINISHED = "finished"  # the result of a game that is over


def ids_text(user_ids) -> str:
    """The users of a game as `|7|12|`: what `Game.player_ids` holds, so that the games of one person are found with a plain LIKE."""
    try:
        ids = sorted({int(user_id) for user_id in user_ids if int(user_id) > 0})
        return f"|{'|'.join(str(user_id) for user_id in ids)}|" if ids else ""
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ids_text failed")
        raise


class Game(Base):
    """One table for the games of a room, of two kinds that are told apart by `status`.

    `live`: the room as it was after its last change (see `snapshots`; sealed when there is a key), one a room, gone with the room.
    `finished`: the result of a game, kept for good: the winner and, for each HUMAN player (a bot seat has no user), the role they
    started with and how they fared. A room that is played again has one live row and a finished row for each game it has seen.
    """

    __tablename__ = "games"
    __table_args__ = (
        Index("ix_games_room", "room_code", "status"),
        Index("uq_games_live_room", "room_code", unique=True, postgresql_where=text("status = 'live'"), sqlite_where=text("status = 'live'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(8))
    state: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # live only: every role and secret action of the game
    winner: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))  # VILLAGER | WOLF | GHOST | DRAW
    days: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    size: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))  # seats, bots included
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # finished only: [{user_id, role ("W:KILL" as `rolecode`), outcome (won|draw|lost), survived, days_survived}]
    players: Mapped[list] = mapped_column(JSON, default=list)
    player_ids: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))  # `|7|12|` (see `ids_text`)
