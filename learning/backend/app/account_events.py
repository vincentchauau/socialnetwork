"""Reactions to account events published by `center` (delivered at least once).

Data model: `courses` (owner_id, owner_username), `enrollments` (user_id,
username, certificate_code), `lesson_completions` (user_id), `quiz_attempts`
(user_id).

Deletion:
- DELETED: the user's enrollments (including their certificate), lesson
  completions and quiz attempts, i.e. all learning progress.
- ANONYMIZED, rows kept: courses authored by the user. Other learners are
  enrolled in them and rely on the content, so deleting is not safe:
  owner_id -> tombstone 0 (center ids start at 1), owner_username ->
  DELETED_USERNAME. Nobody owns them afterwards, so nobody can edit them; the
  published flag is left untouched so enrolled learners keep access.

Rename updates courses.owner_username and enrollments.username.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.models import Course, Enrollment, LessonCompletion, QuizAttempt

DELETED_USERNAME = "Người dùng đã xóa"
DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id == DELETED_USER_ID:
        return
    for model in (Enrollment, LessonCompletion, QuizAttempt):
        db.execute(delete(model).where(model.user_id == user_id))
    db.execute(
        update(Course)
        .where(Course.owner_id == user_id)
        .values(owner_id=DELETED_USER_ID, owner_username=DELETED_USERNAME)
    )


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(update(Course).where(Course.owner_id == user_id).values(owner_username=new_username))
    db.execute(update(Enrollment).where(Enrollment.user_id == user_id).values(username=new_username))
