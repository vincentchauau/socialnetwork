from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

USERNAME_MAX = 32
STORED_NAME_MAX = 64
CONTENT_TYPE_MAX = 32


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Photo(Base):
    __tablename__ = "photos"
    __table_args__ = (Index("ix_photos_user_id_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX), index=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_name: Mapped[str] = mapped_column(String(STORED_NAME_MAX))
    thumb_name: Mapped[str] = mapped_column(String(STORED_NAME_MAX))
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_MAX))
    thumb_content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_MAX))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("photo_id", "user_id", name="uq_likes_photo_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
