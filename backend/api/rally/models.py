from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.rally.db import Base
from sn_shared.clock import utcnow


class Match(Base):
    """A match of one person: its name and the video file it was uploaded as."""

    __tablename__ = "rally_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(100))
    video_name: Mapped[str] = mapped_column(String(255))
    video_path: Mapped[str] = mapped_column(String(500))
    people_status: Mapped[str] = mapped_column(String(16), default="idle")  # idle, running, done or failed
    people_track: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: the samples of the players job
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Rally(Base):
    """One rally: its span in the video (milliseconds), its hits and the side that won the point ("A" or "B")."""

    __tablename__ = "rally_rallies"
    __table_args__ = (UniqueConstraint("match_id", "number", name="uq_rally_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("rally_matches.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(BigInteger)
    end_ms: Mapped[int] = mapped_column(BigInteger)
    hits: Mapped[int] = mapped_column(Integer)
    winner: Mapped[str] = mapped_column(String(1))
