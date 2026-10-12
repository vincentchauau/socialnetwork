"""Reactions to account events published by `center` (delivered at least once).

Data model: `videos` (owner_id, owner), `watch_progress`, `watchlist` and
`video_views` (user_id), plus video files in UPLOAD_DIR.

Deletion removes the user's personal data entirely (no anonymized leftovers):
- the user's videos, with every progress / watchlist / view row other people
  hold for them, and the video files;
- the user's own progress, watchlist and view rows on other people's videos.
Files are removed after the database work, best effort and tolerating files that
are already gone. The caller commits afterwards; if that commit fails the rows
survive and a retry deletes whatever files are left, so a retry stays correct.

Rename updates `videos.owner`.

Both handlers are idempotent, never raise for missing data and never commit.
"""

import os
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Video, VideoView, WatchlistItem, WatchProgress
from app.storage import remove_file

DEFAULT_UPLOAD_DIR = "./uploads"


def on_user_deleted(db: Session, user_id: int) -> None:
    owned = db.execute(select(Video.id, Video.file_name).where(Video.owner_id == user_id)).all()
    video_ids = [row.id for row in owned]
    if video_ids:
        for model in (WatchProgress, WatchlistItem, VideoView):
            db.execute(delete(model).where(model.video_id.in_(video_ids)))
        db.execute(delete(Video).where(Video.id.in_(video_ids)))
    for model in (WatchProgress, WatchlistItem, VideoView):
        db.execute(delete(model).where(model.user_id == user_id))
    upload_dir = Path(os.environ.get("UPLOAD_DIR", DEFAULT_UPLOAD_DIR))
    for row in owned:
        remove_file(upload_dir, row.file_name)


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    db.execute(update(Video).where(Video.owner_id == user_id).values(owner=new_username))
