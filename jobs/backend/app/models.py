from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

TAG_DELIMITER = ","


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def pack_tags(tags: list[str]) -> str:
    """Tags are stored as ',a,b,' so a tag can be matched with a plain LIKE."""
    return f"{TAG_DELIMITER}{TAG_DELIMITER.join(tags)}{TAG_DELIMITER}" if tags else ""


def unpack_tags(packed: str) -> list[str]:
    return [tag for tag in packed.split(TAG_DELIMITER) if tag]


class Posting(Base):
    __tablename__ = "postings"
    __table_args__ = (Index("ix_postings_owner", "owner_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    owner_username: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    employment_type: Mapped[str] = mapped_column(String(16))
    salary_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    description: Mapped[str] = mapped_column(Text, default="")
    tags_text: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(8), default="open")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("posting_id", "applicant_id", name="uq_application_posting_applicant"),
        Index("ix_applications_applicant", "applicant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("postings.id"))
    applicant_id: Mapped[int] = mapped_column(Integer)
    applicant_username: Mapped[str] = mapped_column(String(32))
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="submitted")
    employer_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("postings.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32))
    headline: Mapped[str] = mapped_column(String(120), default="")
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    about: Mapped[str] = mapped_column(Text, default="")
    open_to_work: Mapped[bool] = mapped_column(Boolean, default=False)
