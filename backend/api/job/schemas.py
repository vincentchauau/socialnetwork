from datetime import date, datetime, timezone
from typing import Annotated, Literal

from sn_shared.tags import MAX_TAGS, TAG_MAX, TAG_QUERY_PATTERN as TAG_PATTERN, clean_tag  # noqa: F401  (the limits are those of every app)
from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

TITLE_MAX = 120
COMPANY_MAX = 120
DEPARTMENT_MAX = 120
LOCATION_MAX = 120
DESCRIPTION_MAX = 10_000
SALARY_MAX_VALUE = 10_000_000_000
COVER_LETTER_MAX = 5_000
EMAIL_MAX = 254
NOTE_MAX = 2_000
SNIPPET_MAX = 200
MAX_REQUIREMENTS = 30  # skills required, skills preferred, responsibilities, benefits
MAX_LANGUAGES = 10
LINE_MAX = 300
NAME_MAX = 60
MAX_OPENINGS = 1000
MAX_YEARS = 80
# The resume a person sends with an application: the same words as the profile of the account, in the limits of an application.
HEADLINE_MAX = 120
SUMMARY_MAX = 2_000
MAX_SKILLS = 50
MAX_EXPERIENCE = 30
MAX_EDUCATION = 20
DATE_MAX = 10
ITEM_TEXT_MAX = 2_000

CURRENCY_PATTERN = r"^[A-Z]{3}$"
EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$"

# The kinds of work are those of the profile of an account, so a person's wish and a job's offer name the same things.
EmploymentType = Literal["full_time", "part_time", "contract", "internship", "freelance", "other"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "manager"]
Education = Literal["none", "high_school", "bachelor", "master", "doctorate"]
SkillLevel = Literal["beginner", "intermediate", "advanced", "expert"]
Proficiency = Literal["basic", "conversational", "fluent", "native"]
SalaryPeriod = Literal["hour", "month", "year"]
WorkMode = Literal["remote", "hybrid", "onsite"]
JobStatus = Literal["draft", "open", "paused", "closed", "filled"]
# A step of an application: `submitted` when it is made; the rest are the employer's.
ApplicationStatus = Literal["submitted", "reviewing", "shortlisted", "interview", "offer", "rejected", "hired"]
NON_NULLABLE_UPDATE_FIELDS = (
    "title", "company", "department", "location", "remote", "employment_type", "openings", "currency",
    "description", "tags", "status", "skills_required", "skills_preferred", "languages", "responsibilities", "benefits",
    "company_about", "domain", "timezone", "working_hours", "people_managed", "nationality_required", "requirements",
    "nice_to_have", "hiring_process", "application_requirements",
)


def as_utc(value: datetime) -> datetime:
    """Naive datetimes (SQLite, or clients that omit an offset) are taken as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_future(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    normalised = as_utc(value)
    if normalised <= datetime.now(timezone.utc):
        raise ValueError("expires_at must be in the future")
    return normalised


UtcDatetime = Annotated[datetime, AfterValidator(as_utc)]
FutureDatetime = Annotated[datetime | None, AfterValidator(_require_future)]
Tag = Annotated[str, AfterValidator(clean_tag)]  # the same words of a tag for every app: see `sn_shared.tags`
Salary = Annotated[int, Field(ge=0, le=SALARY_MAX_VALUE)]
Email = Annotated[str, StringConstraints(max_length=EMAIL_MAX, pattern=EMAIL_PATTERN)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LINE_MAX)]


def unique_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tags))  # (the order given, no repeats)


class SkillItem(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    level: SkillLevel | None = None
    years: int | None = Field(default=None, ge=0, le=MAX_YEARS)


class LanguageItem(BaseModel):
    language: str = Field(min_length=1, max_length=NAME_MAX)
    proficiency: Proficiency = "conversational"


class JobDescriptionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    company: str = Field(min_length=1, max_length=COMPANY_MAX)
    department: str = Field(default="", max_length=DEPARTMENT_MAX)
    location: str = Field(default="", max_length=LOCATION_MAX)
    remote: bool = False
    employment_type: EmploymentType
    company_about: str = Field(default="", max_length=2000)
    domain: str = Field(default="", max_length=120)
    work_mode: WorkMode | None = None
    timezone: str = Field(default="", max_length=60)
    working_hours: str = Field(default="", max_length=200)
    contract_until: date | None = None
    people_managed: int = Field(default=0, ge=0, le=500)
    nationality_required: str = Field(default="", max_length=60)
    requirements: str = Field(default="", max_length=4000)
    nice_to_have: str = Field(default="", max_length=4000)
    hiring_process: str = Field(default="", max_length=2000)
    application_requirements: str = Field(default="", max_length=2000)
    seniority: Seniority | None = None
    openings: int = Field(default=1, ge=1, le=MAX_OPENINGS)
    experience_min_years: int | None = Field(default=None, ge=0, le=MAX_YEARS)
    education_min: Education | None = None
    skills_required: list[SkillItem] = Field(default_factory=list, max_length=MAX_REQUIREMENTS)
    skills_preferred: list[SkillItem] = Field(default_factory=list, max_length=MAX_REQUIREMENTS)
    languages: list[LanguageItem] = Field(default_factory=list, max_length=MAX_LANGUAGES)
    responsibilities: list[Line] = Field(default_factory=list, max_length=MAX_REQUIREMENTS)
    benefits: list[Line] = Field(default_factory=list, max_length=MAX_REQUIREMENTS)
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: str = Field(default="USD", pattern=CURRENCY_PATTERN)
    salary_period: SalaryPeriod | None = None
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    tags: list[Tag] = Field(default_factory=list, max_length=MAX_TAGS)
    status: Literal["draft", "open"] = "open"
    expires_at: FutureDatetime = None

    _dedupe_tags = field_validator("tags")(unique_tags)

    @model_validator(mode="after")
    def _salary_range(self) -> "JobDescriptionCreate":
        check_salary_range(self.salary_min, self.salary_max)
        return self


def check_salary_range(minimum: int | None, maximum: int | None) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("salary_min must not exceed salary_max")


class JobDescriptionUpdate(BaseModel):
    """Partial update; what is optional in the job (salary, expiry, seniority...) may be set to null to clear it."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    company: str | None = Field(default=None, min_length=1, max_length=COMPANY_MAX)
    department: str | None = Field(default=None, max_length=DEPARTMENT_MAX)
    location: str | None = Field(default=None, max_length=LOCATION_MAX)
    remote: bool | None = None
    employment_type: EmploymentType | None = None
    company_about: str = Field(default=None, max_length=2000)
    domain: str = Field(default=None, max_length=120)
    work_mode: WorkMode | None = None
    timezone: str = Field(default=None, max_length=60)
    working_hours: str = Field(default=None, max_length=200)
    contract_until: date | None = None
    people_managed: int = Field(default=None, ge=0, le=500)
    nationality_required: str = Field(default=None, max_length=60)
    requirements: str = Field(default=None, max_length=4000)
    nice_to_have: str = Field(default=None, max_length=4000)
    hiring_process: str = Field(default=None, max_length=2000)
    application_requirements: str = Field(default=None, max_length=2000)
    seniority: Seniority | None = None
    openings: int | None = Field(default=None, ge=1, le=MAX_OPENINGS)
    experience_min_years: int | None = Field(default=None, ge=0, le=MAX_YEARS)
    education_min: Education | None = None
    skills_required: list[SkillItem] | None = Field(default=None, max_length=MAX_REQUIREMENTS)
    skills_preferred: list[SkillItem] | None = Field(default=None, max_length=MAX_REQUIREMENTS)
    languages: list[LanguageItem] | None = Field(default=None, max_length=MAX_LANGUAGES)
    responsibilities: list[Line] | None = Field(default=None, max_length=MAX_REQUIREMENTS)
    benefits: list[Line] | None = Field(default=None, max_length=MAX_REQUIREMENTS)
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: str | None = Field(default=None, pattern=CURRENCY_PATTERN)
    salary_period: SalaryPeriod | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    tags: list[Tag] | None = Field(default=None, max_length=MAX_TAGS)
    status: JobStatus | None = None
    expires_at: FutureDatetime = None

    @field_validator("tags")
    @classmethod
    def _dedupe_tags(cls, tags: list[str] | None) -> list[str] | None:
        return None if tags is None else unique_tags(tags)

    @model_validator(mode="after")
    def _no_null_for_required(self) -> "JobDescriptionUpdate":
        for name in NON_NULLABLE_UPDATE_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class JobDescriptionSummary(BaseModel):
    id: int
    title: str
    company: str
    department: str
    location: str
    remote: bool
    employment_type: EmploymentType
    seniority: Seniority | None
    openings: int
    salary_min: int | None
    salary_max: int | None
    currency: str
    salary_period: SalaryPeriod | None
    snippet: str
    tags: list[str]
    status: JobStatus
    expired: bool
    expires_at: UtcDatetime | None
    created_at: UtcDatetime
    owner_username: str
    is_owner: bool
    applied: bool
    application_count: int | None = None


class MatchOut(BaseModel):
    """How well a person fits what the job asks of skills: `score` is 0 to 100 (null when the job asks for none)."""

    score: int | None
    matched: list[str] = []
    partial: list[str] = []  # there, but below the level or the years asked
    missing: list[str] = []
    missing_preferred: list[str] = []


class JobDescriptionDetail(JobDescriptionSummary):
    match: MatchOut | None = None  # the viewer against the job (not for its owner)
    description: str
    experience_min_years: int | None
    education_min: Education | None
    skills_required: list[SkillItem]
    skills_preferred: list[SkillItem]
    languages: list[LanguageItem]
    responsibilities: list[str]
    benefits: list[str]
    company_about: str
    domain: str
    work_mode: WorkMode | None
    timezone: str
    working_hours: str
    contract_until: date | None
    people_managed: int
    nationality_required: str
    requirements: str
    nice_to_have: str
    hiring_process: str
    application_requirements: str


class JobDescriptionPage(BaseModel):
    items: list[JobDescriptionSummary]
    next_cursor: str | None


class ExperienceItem(BaseModel):
    company: str = Field(default="", max_length=NAME_MAX * 2)
    title: str = Field(default="", max_length=NAME_MAX * 2)
    start: str | None = Field(default=None, max_length=DATE_MAX)
    end: str | None = Field(default=None, max_length=DATE_MAX)
    description: str = Field(default="", max_length=ITEM_TEXT_MAX)


class EducationItem(BaseModel):
    school: str = Field(default="", max_length=NAME_MAX * 2)
    degree: str = Field(default="", max_length=NAME_MAX * 2)
    field: str = Field(default="", max_length=NAME_MAX * 2)
    start: str | None = Field(default=None, max_length=DATE_MAX)
    end: str | None = Field(default=None, max_length=DATE_MAX)


class Resume(BaseModel):
    """The resume of a person as it was when they applied: what they chose to show from their profile."""

    headline: str = Field(default="", max_length=HEADLINE_MAX)
    summary: str = Field(default="", max_length=SUMMARY_MAX)
    skills: list[SkillItem] = Field(default_factory=list, max_length=MAX_SKILLS)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=MAX_EXPERIENCE)
    education: list[EducationItem] = Field(default_factory=list, max_length=MAX_EDUCATION)
    languages: list[LanguageItem] = Field(default_factory=list, max_length=MAX_LANGUAGES * 2)


class ApplicationCreate(BaseModel):
    cover_letter: str = Field(default="", max_length=COVER_LETTER_MAX)
    resume: Resume | None = None
    contact_email: Email | None = None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class StepOut(BaseModel):
    status: str
    at: UtcDatetime
    by: Literal["applicant", "employer"]


class ApplicationOut(BaseModel):
    """What the applicant sees: never the employer's private note."""

    id: int
    job_id: int
    job_title: str
    company: str
    status: ApplicationStatus
    cover_letter: str
    resume: Resume | None
    contact_email: str | None
    history: list[StepOut]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ApplicantOut(BaseModel):
    """What the employer sees about one application."""

    id: int
    job_id: int
    applicant_username: str
    status: ApplicationStatus
    cover_letter: str
    resume: Resume | None
    contact_email: str | None
    note: str
    match: MatchOut | None = None  # the resume sent with it, against what the job asks
    history: list[StepOut]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class MyApplicationEdit(BaseModel):
    cover_letter: str | None = Field(default=None, max_length=COVER_LETTER_MAX)
    contact_email: Email | None = None
