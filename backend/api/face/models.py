from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.face.db import Base
from sn_shared.clock import utcnow

NOTE_MAX = 200


class Measurement(Base):
    """Numeric scores only: no image, landmarks, skin metrics or username."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    symmetry: Mapped[int] = mapped_column(Integer)
    eye: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nose: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mouth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ear: Mapped[int | None] = mapped_column(Integer, nullable=True)
    angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(String(NOTE_MAX), default="", server_default="")  # the person's own words about the reading
