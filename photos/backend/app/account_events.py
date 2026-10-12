"""Reactions to account events published by `center` (delivered at least once).

Data model: `photos` (user_id, username), `likes` (user_id), `comments`
(user_id, username), plus image/thumbnail files in UPLOAD_DIR.

Deletion removes the user's personal data entirely (no anonymized leftovers):
- the user's photos, together with every like and comment other people left on
  them, and the image and thumbnail files of those photos;
- the user's likes and comments on other people's photos.
Files are removed after the database work, best effort and tolerating files that
are already gone. The caller commits afterwards; if that commit fails the rows
survive and a retry deletes whatever files are left, so a retry stays correct.

Rename updates `photos.username` and `comments.username`.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Comment, Like, Photo
from app.storage import PhotoStorage


def on_user_deleted(db: Session, user_id: int) -> None:
    owned = db.execute(
        select(Photo.id, Photo.image_name, Photo.thumb_name).where(Photo.user_id == user_id)
    ).all()
    photo_ids = [row.id for row in owned]
    if photo_ids:
        db.execute(delete(Like).where(Like.photo_id.in_(photo_ids)))
        db.execute(delete(Comment).where(Comment.photo_id.in_(photo_ids)))
        db.execute(delete(Photo).where(Photo.id.in_(photo_ids)))
    db.execute(delete(Like).where(Like.user_id == user_id))
    db.execute(delete(Comment).where(Comment.user_id == user_id))
    if owned:
        storage = PhotoStorage.from_env()
        for row in owned:
            storage.delete(row.image_name, row.thumb_name)


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    db.execute(update(Photo).where(Photo.user_id == user_id).values(username=new_username))
    db.execute(update(Comment).where(Comment.user_id == user_id).values(username=new_username))
