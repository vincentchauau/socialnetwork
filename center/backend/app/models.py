from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, Integer, LargeBinary, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.passwords import NO_PASSWORD


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    # Index names must match app.migrate so fresh and upgraded databases are identical.
    __table_args__ = (
        Index("uq_users_email", "email", unique=True),
        Index("uq_users_google_sub", "google_sub", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    audio_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    face_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    biometric_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    @property
    def has_password(self) -> bool:
        return self.password_hash != NO_PASSWORD

    @property
    def has_biometrics(self) -> bool:
        return bool(self.audio_embedding or self.face_embedding)
