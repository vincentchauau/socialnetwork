"""Reactions to account events published by `center` (delivered at least once).

Data model: `postings` (owner_id, owner_username), `applications`
(applicant_id, applicant_username, cover letter, resume, contact email),
`saved_jobs` (user_id), `profiles` (user_id, username).

Deletion:
- DELETED: the user's profile, saved jobs and job applications (personal data
  including resume and contact email).
- ANONYMIZED, rows kept: postings owned by the user. Applicants hold
  applications against them, so deleting would destroy other people's
  history: owner_id -> tombstone 0 (center ids start at 1), owner_username ->
  DELETED_USERNAME and status -> "closed" so no new applications arrive.

Rename updates postings.owner_username, applications.applicant_username and
profiles.username.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.models import Application, Posting, Profile, SavedJob

DELETED_USERNAME = "Người dùng đã xóa"
DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(delete(Application).where(Application.applicant_id == user_id))
    db.execute(delete(SavedJob).where(SavedJob.user_id == user_id))
    db.execute(delete(Profile).where(Profile.user_id == user_id))
    db.execute(
        update(Posting)
        .where(Posting.owner_id == user_id)
        .values(owner_id=DELETED_USER_ID, owner_username=DELETED_USERNAME, status="closed")
    )


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(update(Posting).where(Posting.owner_id == user_id).values(owner_username=new_username))
    db.execute(
        update(Application)
        .where(Application.applicant_id == user_id)
        .values(applicant_username=new_username)
    )
    db.execute(update(Profile).where(Profile.user_id == user_id).values(username=new_username))
