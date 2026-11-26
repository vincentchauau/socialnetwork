from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


from api.job.db import Base
from sn_shared.clock import utcnow


class JobDescription(Base):
    """A job as an employer describes it: who and what it asks for, not only a title and a text."""

    __tablename__ = "job_descriptions"
    __table_args__ = (Index("ix_job_descriptions_owner", "owner_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    # The job as the posting describes it beyond the basics (all optional text, so an old posting reads as empty).
    company_about: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(120), default="")
    work_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)  # remote, hybrid or onsite
    timezone: Mapped[str] = mapped_column(String(60), default="")
    working_hours: Mapped[str] = mapped_column(String(200), default="")
    employment_type: Mapped[str] = mapped_column(String(16))
    contract_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    openings: Mapped[int] = mapped_column(Integer, default=1)
    people_managed: Mapped[int] = mapped_column(Integer, default=0)
    nationality_required: Mapped[str] = mapped_column(String(60), default="")
    # What it asks of a person (the words of a resume: skills with a level, years, languages, education).
    experience_min_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education_min: Mapped[str | None] = mapped_column(String(16), nullable=True)
    skills_required: Mapped[list] = mapped_column(JSON, default=list)  # {name, level, years}
    skills_preferred: Mapped[list] = mapped_column(JSON, default=list)
    skill_keys: Mapped[list] = mapped_column(JSON, default=list)  # the keys of both lists: what a search by skill looks for
    tags: Mapped[list] = mapped_column(JSON, default=list)  # the words the posting is found by
    languages: Mapped[list] = mapped_column(JSON, default=list)  # {language, proficiency}
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)  # lines of text
    requirements: Mapped[str] = mapped_column(Text, default="")
    nice_to_have: Mapped[str] = mapped_column(Text, default="")
    hiring_process: Mapped[str] = mapped_column(Text, default="")
    application_requirements: Mapped[str] = mapped_column(Text, default="")
    benefits: Mapped[list] = mapped_column(JSON, default=list)
    salary_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    salary_period: Mapped[str | None] = mapped_column(String(8), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(8), default="open")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobApplicant(Base):
    """What one person is to one job: the application to it, with its steps. A row is kept only while there is an application."""

    __tablename__ = "job_applications"
    __table_args__ = (
        UniqueConstraint("job_description_id", "user_id", name="uq_job_applicant"),
        Index("ix_job_applicants_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_description_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"))
    user_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cover_letter: Mapped[str] = mapped_column(Text, default="")
    resume: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the resume of the person as it was when they applied
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    employer_note: Mapped[str] = mapped_column(Text, default="")
    history: Mapped[list] = mapped_column(JSON, default=list)  # {status, at, by}: each step of the application (the day it was made and the day it last moved are here)
