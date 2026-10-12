from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_room_id", "room", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
