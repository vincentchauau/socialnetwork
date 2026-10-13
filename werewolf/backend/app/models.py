from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[str] = mapped_column(String(32))
    winner: Mapped[str] = mapped_column(String(16))  # VILLAGER | WOLF | GHOST | DRAW (legacy: village | wolves)
    days: Mapped[int] = mapped_column(Integer)
    size: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))  # seats, bots included
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="result", cascade="all, delete-orphan", order_by="GamePlayer.id"
    )


class GamePlayer(Base):
    """One HUMAN player of a game (a bot seat has no user and is never stored), with the roles they started with."""

    __tablename__ = "game_players"
    __table_args__ = (Index("ix_game_players_user", "user_id", "result_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("game_results.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(16))  # legacy column of the old 4-role game; new rows: faction code
    survived: Mapped[bool] = mapped_column(Boolean)
    faction: Mapped[str] = mapped_column(String(16), default="", server_default=text("''"))
    ability: Mapped[str] = mapped_column(String(24), default="", server_default=text("''"))
    outcome: Mapped[str] = mapped_column(String(8), default="", server_default=text("''"))  # won | draw | lost
    days_survived: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    result: Mapped[GameResult] = relationship(back_populates="players")
