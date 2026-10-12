from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Video, WatchlistItem, WatchProgress, utcnow
from app.routes_videos import VideoId, get_video_or_404
from app.schemas import (
    PAGE_MAX_LIMIT,
    HistoryItem,
    ProgressIn,
    ProgressOut,
    VideoOut,
)
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=PAGE_MAX_LIMIT)]


@router.put("/videos/{video_id}/progress", response_model=ProgressOut)
def save_progress(
    video_id: VideoId,
    body: ProgressIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WatchProgress:
    get_video_or_404(db, video_id)
    record = db.get(WatchProgress, (user.user_id, video_id))
    if record is None:
        record = WatchProgress(user_id=user.user_id, video_id=video_id)
        db.add(record)
    record.seconds = body.seconds
    record.updated_at = utcnow()
    db.commit()
    return record


@router.get("/me/history", response_model=list[HistoryItem])
def history(
    limit: Limit = PAGE_MAX_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[HistoryItem]:
    rows = db.execute(
        select(WatchProgress, Video)
        .join(Video, Video.id == WatchProgress.video_id)
        .where(WatchProgress.user_id == user.user_id)
        .order_by(WatchProgress.updated_at.desc(), WatchProgress.video_id.desc())
        .limit(limit)
    ).all()
    return [
        HistoryItem(
            video=VideoOut.model_validate(video),
            seconds=progress.seconds,
            updated_at=progress.updated_at,
        )
        for progress, video in rows
    ]


@router.put("/videos/{video_id}/watchlist", status_code=status.HTTP_204_NO_CONTENT)
def add_to_watchlist(
    video_id: VideoId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    get_video_or_404(db, video_id)
    if db.get(WatchlistItem, (user.user_id, video_id)) is None:
        db.add(WatchlistItem(user_id=user.user_id, video_id=video_id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/videos/{video_id}/watchlist", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(
    video_id: VideoId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    get_video_or_404(db, video_id)
    db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user.user_id, WatchlistItem.video_id == video_id
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/watchlist", response_model=list[VideoOut])
def watchlist(
    limit: Limit = PAGE_MAX_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Video]:
    return list(
        db.scalars(
            select(Video)
            .join(WatchlistItem, WatchlistItem.video_id == Video.id)
            .where(WatchlistItem.user_id == user.user_id)
            .order_by(WatchlistItem.added_at.desc(), Video.id.desc())
            .limit(limit)
        )
    )
