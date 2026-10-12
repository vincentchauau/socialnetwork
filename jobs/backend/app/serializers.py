from sqlalchemy.orm import Session

from app.models import Application, Posting, Profile, unpack_tags
from app.queries import (
    application_counts,
    applied_ids,
    now_utc,
    saved_ids,
)
from app.schemas import (
    SNIPPET_MAX,
    ApplicantOut,
    ApplicationOut,
    PostingDetail,
    PostingSummary,
    ProfileOut,
    as_utc,
)
from sn_shared.security import TokenPayload


def is_expired(posting: Posting) -> bool:
    return posting.expires_at is not None and as_utc(posting.expires_at) <= now_utc()


def _summary_fields(
    posting: Posting, user: TokenPayload, applied: bool, saved: bool, count: int | None
) -> dict:
    is_owner = posting.owner_id == user.user_id
    return {
        "id": posting.id,
        "title": posting.title,
        "company": posting.company,
        "location": posting.location,
        "remote": posting.remote,
        "employment_type": posting.employment_type,
        "salary_min": posting.salary_min,
        "salary_max": posting.salary_max,
        "currency": posting.currency,
        "snippet": posting.description[:SNIPPET_MAX],
        "tags": unpack_tags(posting.tags_text),
        "status": posting.status,
        "expired": is_expired(posting),
        "expires_at": posting.expires_at,
        "created_at": posting.created_at,
        "owner_username": posting.owner_username,
        "is_owner": is_owner,
        "applied": applied,
        "saved": saved,
        "application_count": count if is_owner else None,
    }


def summaries(db: Session, user: TokenPayload, postings: list[Posting]) -> list[PostingSummary]:
    """Summaries with the caller's applied/saved flags and owner-only counts, in two queries."""
    ids = [posting.id for posting in postings]
    applied = applied_ids(db, user.user_id, ids)
    saved = saved_ids(db, user.user_id, ids)
    owned = [p.id for p in postings if p.owner_id == user.user_id]
    counts = application_counts(db, owned)
    return [
        PostingSummary(
            **_summary_fields(p, user, p.id in applied, p.id in saved, counts.get(p.id, 0))
        )
        for p in postings
    ]


def detail(db: Session, user: TokenPayload, posting: Posting) -> PostingDetail:
    summary = summaries(db, user, [posting])[0]
    return PostingDetail(**summary.model_dump(), description=posting.description)


def application_out(application: Application, posting: Posting) -> ApplicationOut:
    return ApplicationOut(
        id=application.id,
        job_id=posting.id,
        job_title=posting.title,
        company=posting.company,
        status=application.status,
        cover_letter=application.cover_letter,
        resume_text=application.resume_text,
        contact_email=application.contact_email,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def profile_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        username=profile.username,
        headline=profile.headline,
        skills=list(profile.skills or []),
        about=profile.about,
        open_to_work=profile.open_to_work,
    )


def applicant_out(application: Application, profile: Profile | None) -> ApplicantOut:
    return ApplicantOut(
        id=application.id,
        job_id=application.posting_id,
        applicant_username=application.applicant_username,
        status=application.status,
        cover_letter=application.cover_letter,
        resume_text=application.resume_text,
        contact_email=application.contact_email,
        note=application.employer_note,
        created_at=application.created_at,
        updated_at=application.updated_at,
        profile=profile_out(profile) if profile else None,
    )
