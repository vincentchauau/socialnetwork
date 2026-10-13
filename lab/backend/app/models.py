from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

KIND_NOTIFICATION = "notification"
KIND_LOG = "log"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LabEvent(Base):
    """One row per notification (RabbitMQ) or stored log line (Kafka).

    `title` is the notification title or the log level; `body` the notification body or the log message.
    Log rows carry the Kafka partition and offset; (kind, partition, offset) is unique so a redelivered
    message is stored once.
    """

    __tablename__ = "lab_events"
    __table_args__ = (UniqueConstraint("kind", "kafka_partition", "kafka_offset", name="uq_lab_events_kafka"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(String(300))
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    kafka_partition: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kafka_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
