from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

TAG_SEPARATOR = ","


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def encode_tags(tags: list[str]) -> str:
    """Stored as ",a,b," so a tag can be matched exactly with LIKE '%,a,%'."""
    return f"{TAG_SEPARATOR}{TAG_SEPARATOR.join(tags)}{TAG_SEPARATOR}" if tags else ""


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    owner: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    tags_text: Mapped[str] = mapped_column(Text, default="")
    file_name: Mapped[str] = mapped_column(String(64), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer)
    views: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def tags(self) -> list[str]:
        return [tag for tag in self.tags_text.split(TAG_SEPARATOR) if tag]


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (Index("ix_progress_user_updated", "user_id", "updated_at"),)

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    seconds: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VideoView(Base):
    __tablename__ = "video_views"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), primary_key=True)
