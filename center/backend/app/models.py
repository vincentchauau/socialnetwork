from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    # Legacy flag (old passwordless mode): kept, since a column cannot be dropped portably; unused.
    biometric_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    voice_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    webcam_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Opt-in second factor after password/Google; OFF unless the user turns it on.
    biometric_2fa: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Deleting the account deletes its passkeys (ORM cascade here, ON DELETE CASCADE in the table).
    passkeys: Mapped[list["Passkey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Passkey.id"
    )

    @property
    def has_password(self) -> bool:
        return self.password_hash != NO_PASSWORD

    @property
    def google_linked(self) -> bool:
        return self.google_sub is not None

    @property
    def has_biometrics(self) -> bool:
        return bool(self.audio_embedding or self.face_embedding)


class Passkey(Base):
    """One WebAuthn credential. An account may hold several (one per device); all share `user_handle`."""

    __tablename__ = "passkeys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True, index=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    user_handle: Mapped[bytes] = mapped_column(LargeBinary)  # 32 random bytes, same for every passkey of a user
    transports: Mapped[str | None] = mapped_column(String(100), nullable=True)  # comma separated
    name: Mapped[str] = mapped_column(String(64), default="Passkey")
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="passkeys")
