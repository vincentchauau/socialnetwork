"""The optional profile of an account (name, address, a resume-like record): shapes, limits and rules.

Everything is optional and private to the account unless `visibility` says otherwise. The lists are kept as JSON in
the `users` row, so their size and the shape of each item are checked here: the database does not.
"""

from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

MIN_BIRTH_YEAR = 1900
LIST_LIMITS = {
    "links": 10,
    "experience": 30,
    "education": 20,
    "skills": 50,
    "languages": 20,
    "certifications": 30,
    "projects": 30,
}
VISIBILITY_PARTS = (
    "name", "address", "birth_date", "location", "contact", "avatar", "headline",
    "summary", "links", "experience", "education", "skills", "languages", "certifications", "projects",
)  # fmt: skip
VISIBILITY_LEVELS = ("private", "employers", "public")
LINK_KINDS = ("linkedin", "github", "facebook", "portfolio", "other")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "freelance", "other")
SKILL_LEVELS = ("beginner", "intermediate", "advanced", "expert")
PROFICIENCY = ("basic", "conversational", "fluent", "native")

# "2023-05" or "2023-05-17": a resume mostly says month and year.
PartialDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


def _url(value: str | None, max_length: int) -> str | None:
    """An http(s) address only: anything else (javascript:, data:) is refused."""
    if value is None or value == "":
        return None
    if len(value) > max_length:
        raise ValueError(f"The address is longer than {max_length} characters")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Enter a web address starting with http:// or https://")
    return value


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LinkItem(_Item):
    kind: Literal["linkedin", "github", "facebook", "portfolio", "other"] = "other"
    url: str = Field(max_length=300)
    label: str = Field(default="", max_length=60)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return _url(value, 300) or ""


class ExperienceItem(_Item):
    company: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    type: Literal["full_time", "part_time", "contract", "internship", "freelance", "other"] = "full_time"
    location: str = Field(default="", max_length=100)
    start: PartialDate | None = None
    end: PartialDate | None = None  # none: still there
    description: str = Field(default="", max_length=2000)


class EducationItem(_Item):
    school: str = Field(min_length=1, max_length=100)
    degree: str = Field(default="", max_length=100)
    field: str = Field(default="", max_length=100)
    start: PartialDate | None = None
    end: PartialDate | None = None
    grade: str = Field(default="", max_length=40)


class SkillItem(_Item):
    name: str = Field(min_length=1, max_length=60)
    level: Literal["beginner", "intermediate", "advanced", "expert"] | None = None
    years: int | None = Field(default=None, ge=0, le=80)


class LanguageItem(_Item):
    language: str = Field(min_length=1, max_length=60)
    proficiency: Literal["basic", "conversational", "fluent", "native"] = "conversational"


class CertificationItem(_Item):
    name: str = Field(min_length=1, max_length=100)
    issuer: str = Field(default="", max_length=100)
    issued: PartialDate | None = None
    expires: PartialDate | None = None
    url: str = Field(default="", max_length=300)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return _url(value, 300) or ""


class ProjectItem(_Item):
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=100)
    url: str = Field(default="", max_length=300)
    start: PartialDate | None = None
    end: PartialDate | None = None
    description: str = Field(default="", max_length=2000)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return _url(value, 300) or ""


class ProfileBody(BaseModel):
    """What a client may set. A field that is not sent is left alone; `null` (or an empty text) clears it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    headline: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=5000)
    birth_date: date | None = None
    city: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=255)
    links: list[LinkItem] | None = Field(default=None, max_length=LIST_LIMITS["links"])
    experience: list[ExperienceItem] | None = Field(default=None, max_length=LIST_LIMITS["experience"])
    education: list[EducationItem] | None = Field(default=None, max_length=LIST_LIMITS["education"])
    skills: list[SkillItem] | None = Field(default=None, max_length=LIST_LIMITS["skills"])
    languages: list[LanguageItem] | None = Field(default=None, max_length=LIST_LIMITS["languages"])
    certifications: list[CertificationItem] | None = Field(default=None, max_length=LIST_LIMITS["certifications"])
    projects: list[ProjectItem] | None = Field(default=None, max_length=LIST_LIMITS["projects"])
    visibility: dict[str, Literal["private", "employers", "public"]] | None = None

    @field_validator("birth_date")
    @classmethod
    def _birth_date(cls, value: date | None) -> date | None:
        if value is not None and not MIN_BIRTH_YEAR <= value.year <= date.today().year:
            raise ValueError("The birth date is not valid")
        if value is not None and value > date.today():
            raise ValueError("The birth date cannot be in the future")
        return value

    @field_validator("avatar_url")
    @classmethod
    def _avatar(cls, value: str | None) -> str | None:
        return _url(value, 255)

    @field_validator("visibility")
    @classmethod
    def _visibility(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is not None:
            unknown = sorted(set(value) - set(VISIBILITY_PARTS))
            if unknown:
                raise ValueError(f"Unknown part of the profile: {unknown[0]}")
        return value

    @model_validator(mode="after")
    def _clean(self) -> "ProfileBody":
        for field in self.model_fields_set:
            value = getattr(self, field)
            if isinstance(value, str) and value == "":
                setattr(self, field, None)  # an empty text clears the field
        return self


class ProfileOut(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None  # read-only here: set at sign-up or by the phone flow, shown under the "contact" part
    headline: str | None = None
    summary: str | None = None
    birth_date: date | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    avatar_url: str | None = None
    links: list[dict] = []
    experience: list[dict] = []
    education: list[dict] = []
    skills: list[dict] = []
    languages: list[dict] = []
    certifications: list[dict] = []
    projects: list[dict] = []
    visibility: dict[str, str] = {}


PROFILE_FIELDS = tuple(ProfileOut.model_fields)
LIST_FIELDS = tuple(LIST_LIMITS)


def profile_out(user: object) -> ProfileOut:
    """The profile as stored; a list or visibility never set reads as empty."""
    values = {field: getattr(user, field) for field in PROFILE_FIELDS}
    for field in (*LIST_FIELDS, "visibility"):
        if values[field] is None:
            values[field] = {} if field == "visibility" else []
    return ProfileOut(**values)


def apply_profile(user: object, body: ProfileBody) -> None:
    """Set what the body sent (and only that) on the user row; the caller commits."""
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field in LIST_FIELDS and value is not None:
            value = [item.model_dump(mode="json") for item in value]
        setattr(user, field, value)


# ---- the CV: the profile as one page, showing only the parts the viewer may read ----

# Each visibility part and the stored fields it covers.
CV_PART_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "address": ("address",),
    "birth_date": ("birth_date",),
    "location": ("city", "region", "country"),
    "contact": ("phone",),
    "avatar": ("avatar_url",),
    "headline": ("headline",),
    "summary": ("summary",),
    "links": ("links",),
    "experience": ("experience",),
    "education": ("education",),
    "skills": ("skills",),
    "languages": ("languages",),
    "certifications": ("certifications",),
    "projects": ("projects",),
}
# Who may read a part, by the viewer: the owner reads everything; a signed-in person reads "employers" and "public"; anyone reads "public".
CV_READABLE: dict[str, frozenset[str]] = {
    "owner": frozenset(VISIBILITY_LEVELS),
    "employer": frozenset({"employers", "public"}),
    "anyone": frozenset({"public"}),
}


class CvOut(ProfileOut):
    username: str | None = None
    hidden: list[str] = []  # the parts this viewer may not read: their fields are empty here


def cv_of(user: object, viewer: str) -> CvOut:
    """The CV of `user` for a viewer ("owner", "employer" or "anyone"). A part never set is private."""
    values = profile_out(user).model_dump()
    visibility = dict(getattr(user, "visibility", None) or {})
    hidden: list[str] = []
    if viewer != "owner":
        for part, fields in CV_PART_FIELDS.items():
            if visibility.get(part, "private") in CV_READABLE[viewer]:
                continue
            hidden.append(part)
            for field in fields:
                values[field] = [] if field in LIST_FIELDS else None
        values["visibility"] = {}
    return CvOut(**values, username=getattr(user, "username", None), hidden=hidden)
