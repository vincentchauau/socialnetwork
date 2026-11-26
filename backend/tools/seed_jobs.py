"""Job descriptions, the skills they ask for, applications (with their steps) and saved jobs."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.job.applicants import APPLICATION_FLOW
from api.job.models import JobApplicant, JobDescription
from api.job.schemas import Resume
from sn_shared import skills as shared_skills
from sn_shared import tags as shared_tags

from tools.seed_cast import PersonInfo, keys_of
from tools.seed_demo_data.jobs import COVER_LETTERS, EMPLOYER_NOTES, JOBS, SKILL_CATALOG, VI
from tools.seed_env import Env

ADMIN_JOB = 5  # the project manager job belongs to the administrator
# (job index, how far the application went): 16 applications
APPLICATIONS = [
    (0, "interview"), (0, "submitted"), (0, "rejected"), (1, "reviewing"), (1, "submitted"), (1, "offer"),
    (2, "shortlisted"), (2, "submitted"), (3, "interview"), (4, "reviewing"), (4, "submitted"), (4, "rejected"),
    (5, "shortlisted"), (7, "interview"), (8, "reviewing"), (9, "rejected"),
]
ADMIN_APPLIES = 6  # position in APPLICATIONS taken by the administrator
PATHS = {
    "submitted": ["submitted"],
    "reviewing": ["submitted", "reviewing"],
    "shortlisted": ["submitted", "reviewing", "shortlisted"],
    "interview": ["submitted", "reviewing", "interview"],
    "offer": ["submitted", "reviewing", "interview", "offer"],
    "rejected": ["submitted", "reviewing", "rejected"],
}
LEVELS = shared_skills.LEVELS


def job_skills(items: list[dict]) -> list[dict]:
    return [dict(item) for item in items]


def resume_seed_jobs(person: PersonInfo, job: JobDescription) -> dict:
    skills = []
    for item in person.skills[:12]:
        level = item.get("level") if item.get("level") in LEVELS else None
        years = item.get("years") if isinstance(item.get("years"), int) and 0 <= item["years"] <= 80 else None
        skills.append({"name": item["name"][:60], "level": level, "years": years})
    if len(skills) < 2:  # a profile with hardly any skill: the resume shows what they say they can do for this job
        skills += [{"name": s["name"], "level": "intermediate", "years": 1} for s in job.skills_required[:3]]
    return Resume.model_validate({
        "headline": person.headline[:120], "summary": person.summary[:2000], "skills": skills,
        "experience": [], "education": [], "languages": [VI],
    }).model_dump()


def history_seed_jobs(env: Env, state: str, applied_days: float) -> list[dict]:
    path = PATHS[state]
    for before, after in zip(path, path[1:]):
        assert APPLICATION_FLOW.allows(before, after), (before, after)
    moment = env.now - timedelta(days=applied_days)
    steps = []
    for number, name in enumerate(path):
        steps.append({"status": name, "at": min(moment, env.now - timedelta(minutes=30)).isoformat(), "by": "applicant" if number == 0 else "employer"})
        moment += timedelta(days=env.rng.randint(1, 3), hours=env.rng.randint(0, 6))
    return steps


def seed_jobs(env: Env, db: Session) -> str | None:
    companies = [spec["company"] for spec in JOBS]
    if db.scalar(select(func.count()).select_from(JobDescription).where(JobDescription.company.in_(companies))):
        return "the demo jobs are already there"
    shared_skills.register(db, SKILL_CATALOG)
    jobs: list[JobDescription] = []
    for index, spec in enumerate(JOBS):
        wanted = keys_of(s["name"] for s in spec["required"] + spec["preferred"])
        owner = env.cast.admin_or_take(wanted) if index == ADMIN_JOB else env.cast.take(wanted)
        low, high, currency, period = spec["salary"]
        job = JobDescription(
            owner_id=owner.id, title=spec["title"], company=spec["company"], department=spec["department"], location=spec["location"],
            remote=spec["remote"], employment_type=spec["employment_type"], seniority=spec["seniority"], openings=spec["openings"],
            experience_min_years=spec["experience_min_years"], education_min=spec["education_min"],
            skills_required=job_skills(spec["required"]), skills_preferred=job_skills(spec["preferred"]), languages=list(spec["languages"]),
            responsibilities=list(spec["responsibilities"]), benefits=list(spec["benefits"]), salary_min=low, salary_max=high,
            currency=currency, salary_period=period, description=spec["description"], status="open",
            expires_at=env.now + timedelta(days=25 + 7 * index), created_at=env.ago(55 - 5 * index),
        )
        db.add(job)
        db.flush()
        job.tags = shared_tags.clean_tags(spec["tags"])
        names = [i["name"] for i in job.skills_required + job.skills_preferred]
        shared_skills.register(db, names)
        job.skill_keys = shared_skills.keys_of(names)
        jobs.append(job)
    seen: dict[int, set[int]] = {job.id: {job.owner_id} for job in jobs}

    def person_for(position: int, job: JobDescription, allow_admin: bool) -> PersonInfo:
        admin = env.cast.admin
        if allow_admin and admin is not None and admin.id not in seen[job.id]:
            chosen = admin
        else:
            chosen = env.cast.take(keys_of(s["name"] for s in job.skills_required), exclude=seen[job.id])
        seen[job.id].add(chosen.id)
        return chosen

    for position, (job_index, state) in enumerate(APPLICATIONS):
        job = jobs[job_index]
        person = person_for(position, job, position == ADMIN_APPLIES)
        age = (env.now - job.created_at.replace(tzinfo=env.now.tzinfo)).days
        history = history_seed_jobs(env, state, max(2.0, min(age - 1, env.rng.randint(4, 30))))
        skills = ", ".join(i["name"] for i in job.skills_required[:2])
        letter = COVER_LETTERS[position % len(COVER_LETTERS)].format(company=job.company, title=job.title, skills=skills)
        db.add(JobApplicant(
            job_description_id=job.id, user_id=person.id, status=state, cover_letter=letter,
            resume=resume_seed_jobs(person, job), contact_email=f"{person.username.lower()}@example.com",
            employer_note=EMPLOYER_NOTES[position % len(EMPLOYER_NOTES)] if state not in ("submitted",) else "", history=history,
        ))
    return None
