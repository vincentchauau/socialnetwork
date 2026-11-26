from datetime import datetime

from sqlalchemy.orm import Session

from sn_shared import skills as shared_skills
from sn_shared import directory
from sn_shared.directory import Person

from api.job.models import JobApplicant, JobDescription
from api.job.queries import application_counts, my_rows, now_utc
from api.job.schemas import (
    SNIPPET_MAX,
    ApplicantOut,
    ApplicationOut,
    JobDescriptionDetail,
    JobDescriptionSummary,
    MatchOut,
    as_utc,
)
from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)


def step_at(row: JobApplicant, index: int) -> datetime:
    """When the application was made (the first step) or last moved (the last): the days are kept in its history."""
    try:
        history = row.history or []
        return as_utc(datetime.fromisoformat(history[index]["at"])) if history else now_utc()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("step_at failed")
        raise


def is_expired(job: JobDescription) -> bool:
    try:
        return job.expires_at is not None and as_utc(job.expires_at) <= now_utc()
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("is_expired failed")
        raise


def summary_fields(
    job: JobDescription, user: TokenPayload, row: JobApplicant | None, count: int | None, tags: list[str], owner_name: str
) -> dict:
    try:
        is_owner = job.owner_id == user.user_id
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "department": job.department,
            "location": job.location,
            "remote": job.remote,
            "employment_type": job.employment_type,
            "seniority": job.seniority,
            "openings": job.openings,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
            "salary_period": job.salary_period,
            "snippet": job.description[:SNIPPET_MAX],
            "tags": tags,
            "status": job.status,
            "expired": is_expired(job),
            "expires_at": job.expires_at,
            "created_at": job.created_at,
            "owner_username": owner_name,
            "is_owner": is_owner,
            "applied": row is not None and row.status is not None,
            "application_count": count if is_owner else None,
        }
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("summary_fields failed")
        raise


def summaries(db: Session, user: TokenPayload, jobs: list[JobDescription]) -> list[JobDescriptionSummary]:
    """Summaries with the caller's applied/saved flags and owner-only counts, in two queries."""
    try:
        ids = [job.id for job in jobs]
        rows = my_rows(db, user.user_id, ids)
        counts = application_counts(db, [j.id for j in jobs if j.owner_id == user.user_id])
        owners = directory.names(db, [job.owner_id for job in jobs])
        return [JobDescriptionSummary(**summary_fields(j, user, rows.get(j.id), counts.get(j.id, 0), sorted(j.tags or []), owners[j.owner_id])) for j in jobs]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("summaries failed")
        raise


def match_out(result: shared_skills.Match) -> MatchOut | None:
    try:
        return None if result.score is None else MatchOut(**result.__dict__)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("match_out failed")
        raise


def match_for(job: JobDescription, have: list[dict]) -> MatchOut | None:
    """What the job asks of skills against the skills a person has."""
    try:
        return match_out(shared_skills.match(job.skills_required or [], job.skills_preferred or [], have))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("match_for failed")
        raise


def detail(db: Session, user: TokenPayload, job: JobDescription) -> JobDescriptionDetail:
    try:
        summary = summaries(db, user, [job])[0]
        viewer = None if job.owner_id == user.user_id else db.get(Person, user.user_id)
        return JobDescriptionDetail(
            **summary.model_dump(),
            match=match_for(job, viewer.skill_items(own=True) if viewer is not None else []) if job.owner_id != user.user_id else None,
            description=job.description,
            experience_min_years=job.experience_min_years,
            education_min=job.education_min,
            skills_required=job.skills_required or [],
            skills_preferred=job.skills_preferred or [],
            languages=job.languages or [],
            responsibilities=job.responsibilities or [],
            benefits=job.benefits or [],
            company_about=job.company_about or "",
            domain=job.domain or "",
            work_mode=job.work_mode,
            timezone=job.timezone or "",
            working_hours=job.working_hours or "",
            contract_until=job.contract_until,
            people_managed=job.people_managed or 0,
            nationality_required=job.nationality_required or "",
            requirements=job.requirements or "",
            nice_to_have=job.nice_to_have or "",
            hiring_process=job.hiring_process or "",
            application_requirements=job.application_requirements or "",
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("detail failed")
        raise


def application_out(row: JobApplicant, job: JobDescription) -> ApplicationOut:
    try:
        return ApplicationOut(
            id=row.id,
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            status=row.status,
            cover_letter=row.cover_letter,
            resume=row.resume,
            contact_email=row.contact_email,
            history=row.history or [],
            created_at=step_at(row, 0),
            updated_at=step_at(row, -1),
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("application_out failed")
        raise


def applicant_out(row: JobApplicant, job: JobDescription, username: str) -> ApplicantOut:
    try:
        return ApplicantOut(
            id=row.id,
            job_id=row.job_description_id,
            applicant_username=username,
            status=row.status,
            cover_letter=row.cover_letter,
            resume=row.resume,
            contact_email=row.contact_email,
            note=row.employer_note,
            match=match_for(job, (row.resume or {}).get("skills", [])),
            history=row.history or [],
            created_at=step_at(row, 0),
            updated_at=step_at(row, -1),
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("applicant_out failed")
        raise
