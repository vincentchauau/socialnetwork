import logging
import os
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Path, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app import queries
from app.db import Base, get_db, make_engine
from app.images import MAX_UPLOAD_BYTES, InvalidImageError, process_image
from app.models import Comment, Like, Photo
from app.schemas import CAPTION_MAX, CommentIn, CommentOut, LikeState, PhotoOut, PhotoPage
from app.storage import PhotoStorage
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload, get_jwt_secret

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "sqlite:///./photos.db"
FEED_DEFAULT_LIMIT = 20
FEED_MAX_LIMIT = 50
COMMENTS_MAX_LIMIT = 200
USERNAME_MAX = 64
IMAGE_CACHE_CONTROL = "private, max-age=86400, immutable"

Limit = Annotated[int, Query(ge=1, le=FEED_MAX_LIMIT)]
Cursor = Annotated[int | None, Query(ge=1)]
PhotoId = Annotated[int, Path(ge=1)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]
Db = Annotated[Session, Depends(get_db)]


def _get_photo(db: Session, photo_id: int) -> Photo:
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return photo


def _like_count(db: Session, photo_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Like).where(Like.photo_id == photo_id)) or 0


def _read_upload(file: UploadFile) -> bytes:
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The file is larger than 5 MB")
    return raw


def _file_response(storage: PhotoStorage, name: str, content_type: str) -> FileResponse:
    path = storage.resolve(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file not found")
    return FileResponse(
        path,
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": IMAGE_CACHE_CONTROL},
    )


def create_app(database_url: str | None = None) -> FastAPI:
    get_jwt_secret()  # fail at startup, not on the first request
    engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    Base.metadata.create_all(engine)

    app = FastAPI(title="socialnetwork photos")
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    storage = PhotoStorage.from_env()
    app.state.storage = storage

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/photos", response_model=PhotoOut, status_code=status.HTTP_201_CREATED)
    def upload(
        user: CurrentUser,
        db: Db,
        file: Annotated[UploadFile, File()],
        caption: Annotated[str | None, Form(max_length=CAPTION_MAX)] = None,
    ) -> PhotoOut:
        try:
            processed = process_image(_read_upload(file))
        except InvalidImageError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
        image_name, thumb_name = storage.save(processed.data, processed.thumb_data, processed.extension)
        photo = Photo(
            user_id=user.user_id,
            username=user.username,
            caption=(caption or "").strip() or None,
            image_name=image_name,
            thumb_name=thumb_name,
            content_type=processed.content_type,
            thumb_content_type="image/webp",
            width=processed.width,
            height=processed.height,
        )
        try:
            db.add(photo)
            db.commit()
        except Exception:
            db.rollback()
            storage.delete(image_name, thumb_name)
            logger.exception("Could not save photo row")
            raise
        return queries.to_out(db, [photo], user)[0]

    @app.get("/photos", response_model=PhotoPage)
    def feed(user: CurrentUser, db: Db, cursor: Cursor = None, limit: Limit = FEED_DEFAULT_LIMIT) -> PhotoPage:
        return queries.page(db, user, cursor, limit)

    @app.get("/users/{username}/photos", response_model=PhotoPage)
    def user_photos(
        username: Annotated[str, Path(min_length=1, max_length=USERNAME_MAX)],
        user: CurrentUser,
        db: Db,
        cursor: Cursor = None,
        limit: Limit = FEED_DEFAULT_LIMIT,
    ) -> PhotoPage:
        return queries.page(db, user, cursor, limit, username=username)

    @app.get("/photos/{photo_id}", response_model=PhotoOut)
    def get_photo(photo_id: PhotoId, user: CurrentUser, db: Db) -> PhotoOut:
        return queries.to_out(db, [_get_photo(db, photo_id)], user)[0]

    @app.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_photo(photo_id: PhotoId, user: CurrentUser, db: Db) -> Response:
        photo = _get_photo(db, photo_id)
        if photo.user_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own photos")
        names = (photo.image_name, photo.thumb_name)
        db.execute(delete(Like).where(Like.photo_id == photo_id))
        db.execute(delete(Comment).where(Comment.photo_id == photo_id))
        db.delete(photo)
        db.commit()
        storage.delete(*names)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/photos/{photo_id}/image")
    def image(photo_id: PhotoId, _user: CurrentUser, db: Db) -> FileResponse:
        photo = _get_photo(db, photo_id)
        return _file_response(storage, photo.image_name, photo.content_type)

    @app.get("/photos/{photo_id}/thumb")
    def thumb(photo_id: PhotoId, _user: CurrentUser, db: Db) -> FileResponse:
        photo = _get_photo(db, photo_id)
        return _file_response(storage, photo.thumb_name, photo.thumb_content_type)

    @app.put("/photos/{photo_id}/like", response_model=LikeState)
    def like(photo_id: PhotoId, user: CurrentUser, db: Db) -> LikeState:
        _get_photo(db, photo_id)
        existing = db.scalar(select(Like.id).where(Like.photo_id == photo_id, Like.user_id == user.user_id))
        if existing is None:
            try:
                db.add(Like(photo_id=photo_id, user_id=user.user_id))
                db.commit()
            except IntegrityError:  # concurrent duplicate: already liked
                db.rollback()
        return LikeState(liked=True, like_count=_like_count(db, photo_id))

    @app.delete("/photos/{photo_id}/like", response_model=LikeState)
    def unlike(photo_id: PhotoId, user: CurrentUser, db: Db) -> LikeState:
        _get_photo(db, photo_id)
        db.execute(delete(Like).where(Like.photo_id == photo_id, Like.user_id == user.user_id))
        db.commit()
        return LikeState(liked=False, like_count=_like_count(db, photo_id))

    @app.get("/photos/{photo_id}/comments", response_model=list[CommentOut])
    def list_comments(
        photo_id: PhotoId,
        _user: CurrentUser,
        db: Db,
        limit: Annotated[int, Query(ge=1, le=COMMENTS_MAX_LIMIT)] = COMMENTS_MAX_LIMIT,
    ) -> list[Comment]:
        _get_photo(db, photo_id)
        return list(
            db.scalars(select(Comment).where(Comment.photo_id == photo_id).order_by(Comment.id).limit(limit))
        )

    @app.post("/photos/{photo_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
    def add_comment(photo_id: PhotoId, body: CommentIn, user: CurrentUser, db: Db) -> Comment:
        _get_photo(db, photo_id)
        comment = Comment(
            photo_id=photo_id, user_id=user.user_id, username=user.username, content=body.content
        )
        db.add(comment)
        db.commit()
        return comment

    @app.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_comment(comment_id: Annotated[int, Path(ge=1)], user: CurrentUser, db: Db) -> Response:
        comment = db.get(Comment, comment_id)
        if comment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
        photo = db.get(Photo, comment.photo_id)
        is_photo_owner = photo is not None and photo.user_id == user.user_id
        if comment.user_id != user.user_id and not is_photo_owner:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot delete this comment")
        db.delete(comment)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app()
