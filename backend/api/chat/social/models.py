"""The social side: who is whose friend, who blocked whom (one table of edges), reports, notifications, the virtual people each person drew.

A person is a row of `users` of center (read through `sn_shared.directory`): nothing here keeps a copy of one.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Engine, Index, Integer, String, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import logging
logger = logging.getLogger(__name__)



def utcnow() -> datetime:
    try:
        return datetime.now(timezone.utc)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("utcnow failed")
        raise


class Base(DeclarativeBase):
    pass


def ensure_tables(engine: Engine) -> None:
    try:
        Base.metadata.create_all(engine)
        copy_old_edges(engine)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("ensure_tables failed")
        raise


def copy_old_edges(engine: Engine) -> None:
    """Fill `edges` from the three tables it replaced (`social_relationships`, `social_blocks`, `social_companions`), only while it is empty.
    The old tables stay where they are: drop them by hand once this has run."""
    try:
        names = set(inspect(engine).get_table_names())
        with engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM edges LIMIT 1")).first() is not None:
                return
            if "social_relationships" in names:
                conn.execute(text("INSERT INTO edges (src_id, dst_id, kind, status) SELECT requester_id, addressee_id, 'friend', status FROM social_relationships"))
            if "social_blocks" in names:
                conn.execute(text("INSERT INTO edges (src_id, dst_id, kind, status) SELECT user_id, blocked_id, 'block', '' FROM social_blocks"))
            if "social_companions" in names:
                conn.execute(text("INSERT INTO edges (src_id, dst_id, kind, status, released_at) SELECT owner_id, virtual_id, 'companion', '', released_at FROM social_companions"))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("copy_old_edges failed")
        raise


class Edge(Base):
    """One directed link between two people: a friend request (`src` asked `dst`; `status` says how it stands), a block (`src` blocked `dst`) or a companion
    (`src` drew the virtual person `dst`; `released_at` ends it, the row stays). A friendship is one row for a pair, whichever way it was asked."""

    __tablename__ = "edges"
    __table_args__ = (Index("ix_edges_incoming", "dst_id", "kind", "status"),)

    src_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    dst_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    kind: Mapped[str] = mapped_column(String(9), primary_key=True)  # friend | block | companion
    status: Mapped[str] = mapped_column(String(8), default="", server_default="")  # friend: pending | accepted | declined; otherwise ""
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


FRIEND, BLOCK, COMPANION = "friend", "block", "companion"


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_status", "status", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(Integer)  # 0 once the reporter's account is gone
    target_type: Mapped[str] = mapped_column(String(8))  # user | message | room | object
    target_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(16))
    details: Mapped[str] = mapped_column(String(500), default="", server_default="")
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")  # open | reviewed | actioned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user", "user_id", "id"), Index("ix_notifications_actor", "actor_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)  # who it is for
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # who caused it (the person is gone: it goes too)
    kind: Mapped[str] = mapped_column(String(24))  # friend_request | friend_accepted
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
