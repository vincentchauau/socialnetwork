"""Read-side helpers: turn Photo rows into PhotoOut with aggregate counts."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Comment, Like, Photo
from app.schemas import PhotoOut, PhotoPage
from sn_shared.security import TokenPayload


def _counts(db: Session, model: type[Like] | type[Comment], ids: Sequence[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = db.execute(
        select(model.photo_id, func.count()).where(model.photo_id.in_(ids)).group_by(model.photo_id)
    )
    return {photo_id: count for photo_id, count in rows}


def to_out(db: Session, photos: Sequence[Photo], user: TokenPayload) -> list[PhotoOut]:
    ids = [photo.id for photo in photos]
    likes, comments = _counts(db, Like, ids), _counts(db, Comment, ids)
    mine = set(
        db.scalars(select(Like.photo_id).where(Like.user_id == user.user_id, Like.photo_id.in_(ids)))
    ) if ids else set()
    return [
        PhotoOut(
            id=p.id,
            username=p.username,
            caption=p.caption,
            width=p.width,
            height=p.height,
            created_at=p.created_at,
            like_count=likes.get(p.id, 0),
            comment_count=comments.get(p.id, 0),
            liked_by_me=p.id in mine,
            is_mine=p.user_id == user.user_id,
            image_url=f"/photos/{p.id}/image",
            thumb_url=f"/photos/{p.id}/thumb",
        )
        for p in photos
    ]


def page(db: Session, user: TokenPayload, cursor: int | None, limit: int, username: str | None = None) -> PhotoPage:
    """Newest-first page; the cursor is the id of the last photo already seen."""
    query = select(Photo).order_by(Photo.id.desc()).limit(limit + 1)
    if cursor is not None:
        query = query.where(Photo.id < cursor)
    if username is not None:
        query = query.where(Photo.username == username)
    rows = list(db.scalars(query))
    has_more = len(rows) > limit
    shown = rows[:limit]
    return PhotoPage(items=to_out(db, shown, user), next_cursor=shown[-1].id if has_more else None)
