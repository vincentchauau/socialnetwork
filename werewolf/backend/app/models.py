from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GameResult(Base):
    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[str] = mapped_column(String(32))
    winner: Mapped[str] = mapped_column(String(16))
    days: Mapped[int] = mapped_column(Integer)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="result", cascade="all, delete-orphan", order_by="GamePlayer.id"
    )


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (Index("ix_game_players_user", "user_id", "result_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("game_results.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(16))
    survived: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[GameResult] = relationship(back_populates="players")
