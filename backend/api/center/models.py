from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.center.db import Base
from api.center.passwords import NO_PASSWORD
from sn_shared.clock import utcnow


class User(Base):
    __tablename__ = "users"
    # Index names must match app.migrate so fresh and upgraded databases are identical.
    __table_args__ = (
        Index("uq_users_email", "email", unique=True),
        Index("uq_users_google_sub", "google_sub", unique=True),
        Index("uq_users_phone", "phone", unique=True),
        Index("uq_users_username_lower", func.lower(text("username")), unique=True),
        {"sqlite_autoincrement": True},  # ids are never reused (dev SQLite); PostgreSQL sequences never reuse
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # display form, as typed
    # Case-insensitive identity is lower(username), enforced by the unique functional index uq_users_username_lower.
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    # `human` signs in; `virtual` is a person made by the platform (a pool the chat draws companions from): no password,
    # no sign-in of any kind, never a token (see app.virtual and app.sessions.issue_session). Same table, so one namespace of names.
    kind: Mapped[str] = mapped_column(String(8), default="human", server_default="human")
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    audio_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    face_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    voice_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    webcam_login: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Opt-in second factor after password/Google; OFF unless the user turns it on.
    biometric_2fa: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # An address counts as a sign-in method only once verified (Google verifies it itself).
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # True only while `email` is the address Google supplied (unlinking Google then removes it with the link).
    email_from_google: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # E.164, set only once verified (so the unique index guards verified numbers); phone_verified mirrors that.
    phone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # TOTP second factor. Secrets are Fernet tokens (app.totp), never plain; the pending one waits until enabled.
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_pending_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # replay protection
    # When the username was last changed by the user (None: never); a rename is allowed once per 30 days.
    username_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Profile details, all optional and private to the account (never put in a token or sent to another service).
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # full name
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(120), nullable=True)  # one-line introduction
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Lists kept as JSON in the row (no child tables); the API validates their shape and size. Deferred: a sign-in reads
    # the user row often and does not need them, so they are loaded only when touched.
    links: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {kind, url, label}
    experience: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {company, title, type, location, start, end, description}
    education: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {school, degree, field, start, end, grade}
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {name, level, years}
    languages: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {language, proficiency}
    certifications: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {name, issuer, issued, expires, url}
    projects: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # {name, role, url, start, end, description}
    # Who may see each part: {"address": "private", ...}; a part that is not listed is private.
    interests: Mapped[list | None] = mapped_column(JSON, nullable=True, deferred=True)  # short texts: what the person likes
    # The two below are for a virtual person only (the agent plays them): who they are in a story, and how they speak.
    persona_role: Mapped[str | None] = mapped_column(String(200), nullable=True)
    speaking_style: Mapped[str | None] = mapped_column(String(200), nullable=True)
    visibility: Mapped[dict | None] = mapped_column(JSON, nullable=True, deferred=True)
    recovery_codes: Mapped[list["RecoveryCode"]] = relationship(cascade="all, delete-orphan")
    # Deleting the account deletes its passkeys (ORM cascade here, ON DELETE CASCADE in the table).
    passkeys: Mapped[list["Passkey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Passkey.id"
    )
    verification_codes: Mapped[list["VerificationCode"]] = relationship(back_populates="user", cascade="all, delete-orphan")
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


class VerificationCode(Base):
    """A single-use code or link sent to an email address or a phone number (see app.codes).

    channel 'email': purpose 'verify' | 'login' | 'reset' | 'reauth'; a link (token_hash, SHA-256) and optionally a
    6-digit code. channel 'phone': purpose 'verify' | 'login'; a code only. code_hash is a keyed HMAC bound to the row id.
    """

    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(8))  # 'email' | 'phone'
    target: Mapped[str] = mapped_column(String(254))  # the address or the E.164 number it was sent to
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="verification_codes")


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


class QrLogin(Base):
    """A QR sign-in request: a new device asks, a signed-in device approves (see app.qr). Short-lived rows."""

    __tablename__ = "qr_logins"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # request_id: 32 random hex characters
    poll_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 hex of the poll token (never stored in clear)
    verify_code: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|approved|denied|consumed|expired
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    approver_sid: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requester_sid: Mapped[str | None] = mapped_column(String(32), nullable=True)  # cookie session of the requester
    requester_ip: Mapped[str] = mapped_column(String(64), default="")
    requester_user_agent: Mapped[str] = mapped_column(String(200), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # wrong verify codes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
