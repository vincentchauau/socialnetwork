from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, false
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
        {"sqlite_autoincrement": True},  # ids are never reused (dev SQLite); PostgreSQL sequences never reuse
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
    # An address counts as a sign-in method only once verified (Google verifies it itself).
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # True only while `email` is the address Google supplied (unlinking Google then removes it with the link).
    email_from_google: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # TOTP second factor. Secrets are Fernet tokens (app.totp), never plain; the pending one waits until enabled.
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # replay protection
    # When the username was last changed by the user (None: never); a rename is allowed once per 30 days.
    username_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recovery_codes: Mapped[list["RecoveryCode"]] = relationship(cascade="all, delete-orphan")
    # Deleting the account deletes its passkeys (ORM cascade here, ON DELETE CASCADE in the table).
    passkeys: Mapped[list["Passkey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Passkey.id"
    )
    email_tokens: Mapped[list["EmailToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

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


class EmailToken(Base):
    """A single-use email token: link (token_hash) and optionally a 6-digit code (code_hash) in one row."""

    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))  # 'verify' | 'login' | 'reset' | 'reauth'
    email: Mapped[str] = mapped_column(String(254))  # the address the mail was sent to
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # SHA-256 hex
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # keyed HMAC, bound to the row id
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="email_tokens")


class RecoveryCode(Base):
    """One single-use TOTP recovery code, stored only as a keyed HMAC (see app.totp)."""

    __tablename__ = "recovery_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    """One signed-in device. Its `sid` is a claim of the access AND refresh tokens (a refresh keeps it)."""

    __tablename__ = "user_sessions"

    sid: Mapped[str] = mapped_column(String(32), primary_key=True)  # 32 random hex characters
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip: Mapped[str] = mapped_column(String(64), default="")  # as the server saw it
    user_agent: Mapped[str] = mapped_column(String(200), default="")  # truncated
    method: Mapped[str] = mapped_column(String(16))  # primary factor: password|google|email|passkey|voice|webcam|refresh
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class AccountEvent(Base):
    """Outbox row: written in the SAME transaction as the user change, relayed to the Redis stream afterwards."""

    __tablename__ = "account_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32))  # 'user.deleted' | 'user.renamed'
    user_id: Mapped[int] = mapped_column(Integer, index=True)  # no foreign key: the row outlives a deleted user
    payload: Mapped[str] = mapped_column(Text, default="{}")  # JSON text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ReservedUsername(Base):
    """A name its owner gave up: only that owner may take it back until `until`."""

    __tablename__ = "reserved_usernames"

    username: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
