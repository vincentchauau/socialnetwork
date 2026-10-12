from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path as PathParam, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    TAG_SEPARATOR,
    Video,
    VideoView,
    WatchlistItem,
    WatchProgress,
    encode_tags,
)
from app.ranges import RangeNotSatisfiableError, parse_range
from app.schemas import (
    DESCRIPTION_MAX,
    PAGE_DEFAULT_LIMIT,
    PAGE_MAX_LIMIT,
    QUERY_MAX,
    TAG_MAX_LEN,
    TAGS_MAX,
    TITLE_MAX,
    VideoDetail,
    VideoOut,
    VideoPage,
)
from app.storage import UploadError, iter_file, remove_file, save_upload, stored_bytes
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

LIKE_ESCAPE = "!"
MAX_INT64 = 2**63 - 1
VideoId = Annotated[int, PathParam(ge=1, le=MAX_INT64)]


def get_video_or_404(db: Session, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return video


def normalize_tags(raw: list[str] | None) -> list[str]:
    tags = raw or []
    if len(tags) > TAGS_MAX:
        raise HTTPException(422, f"At most {TAGS_MAX} tags are allowed")
    cleaned: list[str] = []
    for tag in tags:
        value = tag.strip().lower()
        if not value or len(value) > TAG_MAX_LEN or TAG_SEPARATOR in value:
            raise HTTPException(422, f"Tags must be 1-{TAG_MAX_LEN} characters without commas")
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _like_escape(value: str) -> str:
    for char in (LIKE_ESCAPE, "%", "_"):
        value = value.replace(char, LIKE_ESCAPE + char)
    return value


def _record_view(db: Session, user_id: int, video: Video) -> None:
    """Count one view per user per video; the primary key makes this race-safe."""
    if db.get(VideoView, (user_id, video.id)) is not None:
        return
    db.add(VideoView(user_id=user_id, video_id=video.id))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return
    db.execute(update(Video).where(Video.id == video.id).values(views=Video.views + 1))
    db.commit()
    db.refresh(video)


def _enforce_quota(request: Request, db: Session, user_id: int) -> int:
    """Refuse the upload if the user is at a limit; return the byte budget left for this file."""
    state = request.app.state
    names = list(db.scalars(select(Video.file_name).where(Video.owner_id == user_id)))
    if len(names) >= state.max_videos_per_user:
        raise HTTPException(409, f"Video limit reached ({state.max_videos_per_user} per user); delete a video first")
    remaining = state.max_user_bytes - stored_bytes(state.upload_dir, names)
    if remaining <= 0:
        raise HTTPException(409, "Storage quota exceeded; delete a video first")
    return min(remaining, state.max_video_bytes)


@router.post("/videos", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def upload_video(
    request: Request,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=TITLE_MAX)],
    rights_confirmed: Annotated[bool, Form()],
    description: Annotated[str, Form(max_length=DESCRIPTION_MAX)] = "",
    tags: Annotated[list[str] | None, Form()] = None,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Video:
    if not rights_confirmed:
        raise HTTPException(422, "You must confirm you own or have the licence to share this video")
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(422, "Title must not be blank")
    clean_tags = normalize_tags(tags)

    upload_dir: Path = request.app.state.upload_dir
    max_bytes = _enforce_quota(request, db, user.user_id)
    try:
        stored = save_upload(file.file, upload_dir, max_bytes)
    except UploadError as error:
        if error.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE and max_bytes < request.app.state.max_video_bytes:
            raise HTTPException(409, "Storage quota exceeded; delete a video first") from None
        raise HTTPException(error.status_code, error.detail) from None
    video = Video(
        owner_id=user.user_id,
        owner=user.username,
        title=clean_title,
        description=description.strip(),
        tags_text=encode_tags(clean_tags),
        file_name=stored.name,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
    )
    try:
        db.add(video)
        db.commit()
    except BaseException:
        remove_file(upload_dir, stored.name)
        raise
    return video


@router.get("/videos", response_model=VideoPage)
def list_videos(
    cursor: Annotated[int | None, Query(ge=1, le=MAX_INT64)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX_LIMIT)] = PAGE_DEFAULT_LIMIT,
    q: Annotated[str | None, Query(max_length=QUERY_MAX)] = None,
    tag: Annotated[str | None, Query(max_length=TAG_MAX_LEN)] = None,
    _user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoPage:
    query = select(Video).order_by(Video.id.desc()).limit(limit + 1)
    if cursor is not None:
        query = query.where(Video.id < cursor)
    if q and q.strip():
        pattern = f"%{_like_escape(q.strip().lower())}%"
        query = query.where(
            Video.title.ilike(pattern, escape=LIKE_ESCAPE)
            | Video.tags_text.like(pattern, escape=LIKE_ESCAPE)
        )
    if tag and tag.strip():
        exact = f"%{TAG_SEPARATOR}{_like_escape(tag.strip().lower())}{TAG_SEPARATOR}%"
        query = query.where(Video.tags_text.like(exact, escape=LIKE_ESCAPE))
    rows = list(db.scalars(query))
    page = rows[:limit]
    next_cursor = page[-1].id if len(rows) > limit else None
    return VideoPage(items=[VideoOut.model_validate(v) for v in page], next_cursor=next_cursor)


@router.get("/videos/{video_id}", response_model=VideoDetail)
def get_video(
    video_id: VideoId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VideoDetail:
    video = get_video_or_404(db, video_id)
    _record_view(db, user.user_id, video)
    progress = db.get(WatchProgress, (user.user_id, video_id))
    listed = db.get(WatchlistItem, (user.user_id, video_id)) is not None
    return VideoDetail(
        **VideoOut.model_validate(video).model_dump(),
        in_watchlist=listed,
        progress_seconds=progress.seconds if progress else 0.0,
    )


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: VideoId,
    request: Request,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    video = get_video_or_404(db, video_id)
    if video.owner_id != user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own videos")
    file_name = video.file_name
    for table in (WatchProgress, WatchlistItem, VideoView):
        db.execute(delete(table).where(table.video_id == video_id))
    db.delete(video)
    db.commit()
    remove_file(request.app.state.upload_dir, file_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/videos/{video_id}/stream")
def stream_video(
    video_id: VideoId,
    request: Request,
    _user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    video = get_video_or_404(db, video_id)
    path: Path = request.app.state.upload_dir / video.file_name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video file is missing")
    size = path.stat().st_size
    headers = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    try:
        byte_range = parse_range(request.headers.get("range"), size)
    except RangeNotSatisfiableError:
        headers["Content-Range"] = f"bytes */{size}"
        return Response(status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE, headers=headers)
    if byte_range is None:
        start, end, code = 0, size - 1, status.HTTP_200_OK
    else:
        (start, end), code = byte_range, status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    headers["Content-Length"] = str(end - start + 1)
    return StreamingResponse(
        iter_file(path, start, end),
        status_code=code,
        media_type=video.content_type,
        headers=headers,
    )
