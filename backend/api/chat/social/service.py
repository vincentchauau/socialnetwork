"""The rules of the social side, apart from HTTP: who may see whom, friendships, blocks, reports, notifications."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from sn_shared.directory import Person

from api.chat.social.models import BLOCK, FRIEND, Edge, Notification, Report

import logging
logger = logging.getLogger(__name__)

MAX_REQUESTS_PER_DAY = 30  # friend requests one person may send in 24 hours
MAX_PENDING_OUT = 100  # and have waiting at any time
MAX_REPORTS_PER_HOUR = 10

REPORT_REASONS = ("spam", "abuse", "impersonation", "illegal", "other")

# What a person is to me (`relation`): nothing yet, friends, someone I asked, someone who asked me.
NONE, FRIENDS, REQUESTED, INCOMING = "none", "friends", "requested", "incoming"

CANNOT_MESSAGE = "You cannot message this person"  # the same words whoever blocked whom


def now() -> datetime:
    try:
        return datetime.now(UTC)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("now failed")
        raise


# ---- people ----------------------------------------------------------------------------------------------------


def actor_of(db: Session, user_id: int, username: str) -> Person | SimpleNamespace:
    """Who did something, for a notice or a rule: the person, or just the id and name of the token when `users` does not hold them."""
    try:
        return db.get(Person, user_id) or SimpleNamespace(user_id=user_id, username=username, kind="human")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("actor_of failed")
        raise


def person_by_name(db: Session, username: str) -> Person | None:
    try:
        return db.scalar(select(Person).where(func.lower(Person.username) == username.lower(), Person.kind != "system"))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("person_by_name failed")
        raise


# ---- blocks ----------------------------------------------------------------------------------------------------


def between(a: int, b: int):
    """The edges that join the two, whichever way they point."""
    try:
        return or_(and_(Edge.src_id == a, Edge.dst_id == b), and_(Edge.src_id == b, Edge.dst_id == a))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("between failed")
        raise


def blocked_between(db: Session, a: int, b: int) -> bool:
    """One of the two blocked the other."""
    try:
        return db.scalar(select(Edge.src_id).where(Edge.kind == BLOCK, between(a, b)).limit(1)) is not None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("blocked_between failed")
        raise


def blocked_by(db: Session, me: int, other: int) -> bool:
    try:
        return db.get(Edge, (me, other, BLOCK)) is not None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("blocked_by failed")
        raise


def blocked_ids(db: Session, me: int) -> set[int]:
    """Everybody who must not meet me: those I blocked and those who blocked me."""
    try:
        mine = set(db.scalars(select(Edge.dst_id).where(Edge.kind == BLOCK, Edge.src_id == me)))
        theirs = set(db.scalars(select(Edge.src_id).where(Edge.kind == BLOCK, Edge.dst_id == me)))
        return mine | theirs
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("blocked_ids failed")
        raise


def block(db: Session, me: int, other: int) -> None:
    """Block: whatever friendship or request there was is gone."""
    try:
        if db.get(Edge, (me, other, BLOCK)) is None:
            db.add(Edge(src_id=me, dst_id=other, kind=BLOCK))
        drop_relationship(db, me, other)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("block failed")
        raise


def unblock(db: Session, me: int, other: int) -> None:
    try:
        db.execute(delete(Edge).where(Edge.kind == BLOCK, Edge.src_id == me, Edge.dst_id == other))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("unblock failed")
        raise


# ---- friendships -----------------------------------------------------------------------------------------------


def relationship_of(db: Session, a: int, b: int) -> Edge | None:
    """The friend row of the pair, whichever way it was asked."""
    try:
        return db.scalar(select(Edge).where(Edge.kind == FRIEND, between(a, b)))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("relationship_of failed")
        raise


def relation(db: Session, me: int, other: int) -> str:
    try:
        row = relationship_of(db, me, other)
        if row is None or row.status == "declined":
            return NONE
        if row.status == "accepted":
            return FRIENDS
        return REQUESTED if row.src_id == me else INCOMING
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("relation failed")
        raise


def friend_person(db: Session, me: int, other: int) -> Person | None:
    """`other` as a person, when we are friends (else None)."""
    try:
        row = relationship_of(db, me, other)
        return db.get(Person, other) if row is not None and row.status == "accepted" else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("friend_person failed")
        raise


def drop_relationship(db: Session, a: int, b: int) -> None:
    try:
        db.execute(delete(Edge).where(Edge.kind == FRIEND, between(a, b)))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("drop_relationship failed")
        raise


class Refused(Exception):
    """A rule says no: `status` is the HTTP status, the message says why."""

    def __init__(self, status: int, message: str) -> None:
        try:
            super().__init__(message)
            self.status = status
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("__init__ failed")
            raise


def request_friendship(db: Session, me: Person, other: Person) -> str:
    """`me` asks `other` to be friends. Returns what they are now (`requested`; `friends` when `other` had asked first, or is a virtual person)."""
    try:
        if me.user_id == other.user_id:
            raise Refused(422, "Choose someone else")
        if blocked_between(db, me.user_id, other.user_id):
            raise Refused(403, CANNOT_MESSAGE)
        row = relationship_of(db, me.user_id, other.user_id)
        if row is not None and row.status == "accepted":
            raise Refused(409, "You are friends already")
        if other.kind == "virtual":  # nobody there to answer: it is friends at once (and nothing to notify)
            if row is not None:
                db.delete(row)
                db.flush()
            db.add(Edge(src_id=me.user_id, dst_id=other.user_id, kind=FRIEND, status="accepted"))
            return FRIENDS
        if row is not None and row.status == "pending":
            if row.src_id == other.user_id:  # they asked first: this is the yes
                accept(db, me, other)
                return FRIENDS
            raise Refused(409, "You have asked already")
        since = now() - timedelta(days=1)
        asked = db.scalar(  # the notice each request leaves is the record of when it was made
            select(func.count()).select_from(Notification).where(Notification.actor_id == me.user_id, Notification.kind == "friend_request", Notification.created_at > since)
        ) or 0
        waiting = db.scalar(select(func.count()).select_from(Edge).where(Edge.kind == FRIEND, Edge.src_id == me.user_id, Edge.status == "pending")) or 0
        if asked >= MAX_REQUESTS_PER_DAY or waiting >= MAX_PENDING_OUT:
            raise Refused(429, "Too many friend requests")
        if row is not None:  # a refused one is asked again: the old row is the same pair
            db.delete(row)
            db.flush()
        db.add(Edge(src_id=me.user_id, dst_id=other.user_id, kind=FRIEND, status="pending"))
        notify(db, other.user_id, "friend_request", me)
        return REQUESTED
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("request_friendship failed")
        raise


def accept(db: Session, me: Person, other: Person) -> None:
    try:
        row = relationship_of(db, me.user_id, other.user_id)
        if row is None or row.status != "pending" or row.dst_id != me.user_id:
            raise Refused(404, "No request from this person")
        row.status = "accepted"
        notify(db, other.user_id, "friend_accepted", me)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("accept failed")
        raise


def decline(db: Session, me: Person, other: Person) -> None:
    try:
        row = relationship_of(db, me.user_id, other.user_id)
        if row is None or row.status != "pending" or row.dst_id != me.user_id:
            raise Refused(404, "No request from this person")
        row.status = "declined"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("decline failed")
        raise


# ---- search ----------------------------------------------------------------------------------------------------


# ---- reports ---------------------------------------------------------------------------------------------------


def report(db: Session, reporter: int, target_type: str, target_id: str, reason: str, details: str) -> tuple[Report, bool]:
    """A report; the same person reporting the same thing again while it is open changes nothing (returns the first one)."""
    try:
        existing = db.scalar(
            select(Report).where(Report.reporter_id == reporter, Report.target_type == target_type, Report.target_id == target_id, Report.status == "open")
        )
        if existing is not None:
            return existing, False
        recent = db.scalar(select(func.count()).select_from(Report).where(Report.reporter_id == reporter, Report.created_at > now() - timedelta(hours=1))) or 0
        if recent >= MAX_REPORTS_PER_HOUR:
            raise Refused(429, "Too many reports")
        row = Report(reporter_id=reporter, target_type=target_type, target_id=target_id, reason=reason, details=details.strip())
        db.add(row)
        db.flush()
        return row, True
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("report failed")
        raise


# ---- notifications ---------------------------------------------------------------------------------------------


def notify(db: Session, user_id: int, kind: str, actor: Person, **extra: str) -> None:
    """A notice for `user_id` about what `actor` did (`extra`: more for the page to link to, such as the slug of a chat)."""
    try:
        db.add(Notification(user_id=user_id, actor_id=actor.user_id, kind=kind, payload={"user_id": actor.user_id, **extra}))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("notify failed")
        raise


def unread_count(db: Session, user_id: int) -> int:
    try:
        return db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))) or 0
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("unread_count failed")
        raise


