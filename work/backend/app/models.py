from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CallEvent(Base):
    """A Telnyx call event. Only masked numbers (all but the last 2 digits) and the payload size are kept."""

    __tablename__ = "call_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telnyx_event_id: Mapped[str] = mapped_column(String(100), unique=True)  # idempotency key
    event_type: Mapped[str] = mapped_column(String(64))
    call_control_id: Mapped[str] = mapped_column(String(200), default="")
    from_number_masked: Mapped[str] = mapped_column(String(32), default="")
    to_number_masked: Mapped[str] = mapped_column(String(32), default="")
    payload_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
