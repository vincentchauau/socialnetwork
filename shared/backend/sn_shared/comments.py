"""Comments: what people say about a thing (a photo, a product, a course, a job), and the stars they give it.

One table (`comments`) holds them all: what kind of thing (`object_type`), which one (`object_id`), who said it, the words and,
where the kind of thing asks for it, a rating from 1 to 5. An app that has comments describes how its kind works in a
`CommentKind` and mounts `comments_router(kind)`: the same four routes, the same limits and the same answers everywhere:

    PHOTOS = CommentKind("photo", "/photos/{object_id}/comments", "/comments/{comment_id}", visible=visible_photo, ...)
    app.include_router(comments_router(PHOTOS))

What differs between kinds is only in the kind: who may write (`may_write`), whether it is one a person (`once`), whether a rating is
asked for (`rating`), whether the owner of the thing may delete what others said (`moderator`), and whether somebody else's comment
looks like it is not there (`others_are_hidden`).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import Boolean, DateTime, Engine, Index, Integer, String, Text, delete, func, select, text, update
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from sn_shared.db import get_db
from sn_shared.directory import attach_names
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

RATING_MIN = 1
RATING_MAX = 5
MAX_ID = 2**63 - 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_object", "object_type", "object_id", "id"),
        Index("ix_comments_user", "user_id"),
        # one comment a person for the kinds that ask for it (a review is given once)
        Index("uq_comment_once", "object_type", "object_id", "user_id", unique=True, postgresql_where=text("once"), sqlite_where=text("once")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(16))
    object_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    once: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def ensure_table(engine: Engine) -> None:
    Base.metadata.create_all(engine)


# ---- what an app says about its kind of thing ---------------------------------------------------------------------


@dataclass(frozen=True)
class CommentKind:
    object_type: str  # what the comments are about: "photo", "product"...
    collection: str  # the path of the comments of one thing, with `{object_id}`: "/photos/{object_id}/comments"
    item: str  # the path of one comment, with `{comment_id}`: "/comments/{comment_id}"
    visible: Callable[[Session, int, TokenPayload], Any]  # the thing, or raise 404 when this person may not see it
    rating: Literal["none", "optional", "required"] = "none"
    once: bool = False  # one comment a person for each thing
    content_min: int = 0
    content_max: int = 1000
    page_default: int = 50
    page_max: int = 200
    newest_first: bool = False
    may_write: Callable[[Session, Any, TokenPayload], None] | None = None  # raise 403 when this person may not comment on the thing
    moderator: Callable[[Any, TokenPayload], bool] | None = None  # may this person delete what others said about the thing?
    others_are_hidden: bool = False  # somebody else's comment looks like none (404) instead of being refused (403)
    strict_body: bool = False  # a field that is not known is refused (422) instead of being ignored
    tag: str = "comments"


# ---- the bodies and answers ---------------------------------------------------------------------------------------


class CommentIn(BaseModel):
    content: str | None = None
    rating: StrictInt | None = Field(default=None, ge=RATING_MIN, le=RATING_MAX)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    object_id: int
    username: str
    content: str
    rating: int | None
    created_at: datetime
    edited_at: datetime | None


def invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, message)


def checked_content(kind: CommentKind, value: str | None) -> str:
    content = (value or "").strip()
    if len(content) < kind.content_min:
        raise invalid("Write something" if kind.content_min else "The comment is too short")
    if len(content) > kind.content_max:
        raise invalid(f"A comment is at most {kind.content_max} characters")
    return content


# ---- the routes ---------------------------------------------------------------------------------------------------


def check_rating(kind: CommentKind, rating: int | None) -> None:
    """A kind of comment with no rating refuses one; a kind that needs a rating refuses none."""
    if kind.rating == "none" and rating is not None:
        raise invalid("This kind of comment has no rating")
    if kind.rating == "required" and rating is None:
        raise invalid("Give a rating")


def may_moderate(kind: CommentKind, db: Session, comment: Comment, user: TokenPayload) -> bool:
    """The owner of the thing may delete what others said about it, when the kind allows it."""
    if kind.moderator is None:
        return False
    try:
        return bool(kind.moderator(kind.visible(db, comment.object_id, user), user))
    except HTTPException:
        return False


def comments_router(kind: CommentKind) -> APIRouter:
    router = APIRouter(tags=[kind.tag])

    class Body(CommentIn):
        model_config = ConfigDict(extra="forbid" if kind.strict_body else "ignore")

    ObjectId = Annotated[int, Path(ge=1, le=MAX_ID)]
    CommentId = Annotated[int, Path(ge=1, le=MAX_ID)]
    Db = Annotated[Session, Depends(get_db)]
    User = Annotated[TokenPayload, Depends(get_current_user)]

    def own_kind(db: Session, comment_id: int) -> Comment:
        comment = db.get(Comment, comment_id)
        if comment is None or comment.object_type != kind.object_type:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
        return comment

    @router.get(kind.collection, response_model=list[CommentOut])
    def list_comments(
        object_id: ObjectId,
        user: User,
        db: Db,
        cursor: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
        limit: Annotated[int | None, Query(ge=1)] = None,
    ) -> list[Comment]:
        kind.visible(db, object_id, user)
        size = min(limit or kind.page_default, kind.page_max)
        query = select(Comment).where(Comment.object_type == kind.object_type, Comment.object_id == object_id)
        if cursor is not None:
            query = query.where(Comment.id < cursor if kind.newest_first else Comment.id > cursor)
        return attach_names(db, db.scalars(query.order_by(Comment.id.desc() if kind.newest_first else Comment.id).limit(size)))

    @router.post(kind.collection, response_model=CommentOut, status_code=status.HTTP_201_CREATED)
    def add_comment(object_id: ObjectId, body: Body, user: User, db: Db) -> Comment:
        thing = kind.visible(db, object_id, user)
        if kind.may_write is not None:
            kind.may_write(db, thing, user)
        content = checked_content(kind, body.content)
        check_rating(kind, body.rating)
        if not content and body.rating is None:
            raise invalid("Write something or give a rating")
        if kind.once and db.scalar(
            select(Comment.id).where(Comment.object_type == kind.object_type, Comment.object_id == object_id, Comment.user_id == user.user_id)
        ) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "You already said something about this")
        comment = Comment(
            object_type=kind.object_type, object_id=object_id, user_id=user.user_id, content=content,
            rating=body.rating, once=kind.once,
        )
        db.add(comment)
        try:
            db.commit()
        except Exception as error:  # a second one at the same moment is stopped by the unique index
            db.rollback()
            if kind.once:
                raise HTTPException(status.HTTP_409_CONFLICT, "You already said something about this") from error
            raise
        attach_names(db, [comment])
        return comment

    @router.patch(kind.item, response_model=CommentOut)
    def change_comment(comment_id: CommentId, body: Body, user: User, db: Db) -> Comment:
        comment = own_kind(db, comment_id)
        if comment.user_id != user.user_id:
            if kind.others_are_hidden:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own comments")
        sent = body.model_fields_set
        if "content" in sent:
            comment.content = checked_content(kind, body.content)
        if "rating" in sent:
            check_rating(kind, body.rating)
            comment.rating = body.rating
        comment.edited_at = utcnow()
        db.commit()
        attach_names(db, [comment])
        return comment

    @router.delete(kind.item, status_code=status.HTTP_204_NO_CONTENT)
    def remove_comment(comment_id: CommentId, user: User, db: Db) -> Response:
        comment = own_kind(db, comment_id)
        if comment.user_id != user.user_id and not may_moderate(kind, db, comment, user):
            if kind.others_are_hidden:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot delete this comment")
        db.delete(comment)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


# ---- what the app that owns the thing asks about its comments -------------------------------------------------------


def counts(db: Session, object_type: str, ids: Iterable[int]) -> dict[int, int]:
    """How many comments each of these things has (a thing with none is not in the result)."""
    ids = list(ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Comment.object_id, func.count()).where(Comment.object_type == object_type, Comment.object_id.in_(ids)).group_by(Comment.object_id)
    )
    return {object_id: count for object_id, count in rows}


def rating_stats(db: Session, object_type: str, ids: Iterable[int]) -> dict[int, tuple[float, int]]:
    """(average, how many) of the ratings of each of these things; a thing nobody rated is not in the result."""
    ids = list(ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Comment.object_id, func.avg(Comment.rating), func.count(Comment.rating))
        .where(Comment.object_type == object_type, Comment.object_id.in_(ids), Comment.rating.is_not(None))
        .group_by(Comment.object_id)
    )
    return {object_id: (float(average), count) for object_id, average, count in rows}


def forget_object(db: Session, object_type: str, object_id: int) -> None:
    """The thing is gone: so are what was said about it (the caller commits)."""
    db.execute(delete(Comment).where(Comment.object_type == object_type, Comment.object_id == object_id))


def forget_user(db: Session, user_id: int, object_types: Iterable[str]) -> None:
    """The account is gone: so are its comments on these kinds of thing."""
    db.execute(delete(Comment).where(Comment.user_id == user_id, Comment.object_type.in_(list(object_types))))


def anonymize_user(db: Session, user_id: int, object_types: Iterable[str]) -> None:
    """The account is gone, but what it said stays for the others to read (a review): with no name, and an id of nobody that is
    still its own (the opposite of the old one), so that the one-a-person rule keeps holding."""
    db.execute(
        update(Comment)
        .where(Comment.user_id == user_id, Comment.object_type.in_(list(object_types)))
        .values(user_id=-user_id)
    )
