"""Face measurements, friend requests with their notices, reports, call events, video jobs and searchable documents."""

from datetime import timedelta

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from api.face.models import Measurement
from api.chat.social import service as social
from api.chat.social.models import FRIEND, Edge, Notification, Report

from tools.seed_demo_data.misc import FACE_SERIES, REPORTS
from tools.seed_env import Env

FRIEND_PAIRS = 8  # four accepted (two notices each), four waiting (one notice each): 12 notices
ACCEPTED_PAIRS = 4
SCENE_SECONDS = 8


def seed_face(env: Env, db: Session) -> str | None:
    notes = {row[6] for series in FACE_SERIES for row in series if row[6]}
    if db.scalar(select(func.count()).select_from(Measurement).where(Measurement.note.in_(notes))):
        return "the demo measurements are already there"
    owners = [env.cast.admin or env.cast.take()]
    for _ in range(len(FACE_SERIES) - 1):
        owners.append(env.cast.take(exclude={o.id for o in owners}))
    for owner, series in zip(owners, FACE_SERIES):
        age = 52 - 4 * len(owners)
        for symmetry, eye, nose, mouth, ear, angle, note in series:
            db.add(Measurement(user_id=owner.id, created_at=env.ago(age), symmetry=symmetry, eye=eye, nose=nose, mouth=mouth, ear=ear, angle=angle, note=note))
            age = max(age - env.rng.randint(5, 12), 1)
    return None


def free_pair(db: Session, a: int, b: int) -> bool:
    return a != b and social.relationship_of(db, a, b) is None and not social.blocked_between(db, a, b)


def seed_friends(env: Env, db: Session) -> str | None:
    if db.scalar(select(func.count()).select_from(Report).where(Report.details.in_([r[1] for r in REPORTS]))):
        return "the demo reports are already there"
    recipients = ([env.cast.admin] if env.cast.admin else []) + [h for h in env.cast.humans if h is not env.cast.admin][:2]
    if not recipients:
        return "there is no human to receive friend requests"
    askers: set[int] = set()
    made = 0
    for _attempt in range(FRIEND_PAIRS * 3):  # a few more tries than pairs: some pairs are taken already
        if made == FRIEND_PAIRS:
            break
        recipient = recipients[made % len(recipients)]
        asker = env.cast.take(exclude={recipient.id, *askers})
        if not free_pair(db, asker.id, recipient.id):
            askers.add(asker.id)
            continue
        askers.add(asker.id)
        accepted = made < ACCEPTED_PAIRS
        asked_at = env.ago(50 - 5 * made)
        db.add(Edge(src_id=asker.id, dst_id=recipient.id, kind=FRIEND, status="accepted" if accepted else "pending"))
        db.add(Notification(
            user_id=recipient.id, actor_id=asker.id, kind="friend_request", payload={"user_id": asker.id},
            read_at=asked_at + timedelta(hours=3) if accepted or made == ACCEPTED_PAIRS else None, created_at=asked_at,
        ))
        if accepted:
            answered = asked_at + timedelta(days=1, hours=2)
            db.add(Notification(
                user_id=asker.id, actor_id=recipient.id, kind="friend_accepted", payload={"user_id": recipient.id},
                read_at=answered + timedelta(hours=5) if made % 2 == 0 else None, created_at=answered,
            ))
        made += 1
    reporters = [env.cast.admin or env.cast.take(), env.cast.take(), env.cast.take(), env.cast.take()]
    for number, ((reason, details, status, kind), reporter) in enumerate(zip(REPORTS, reporters)):
        kind, target = report_target(env, db, kind, reporter.id)
        db.add(Report(reporter_id=reporter.id, target_type=kind, target_id=target, reason=reason, details=details, status=status, created_at=env.ago(40 - 9 * number)))
    return None


def report_target(env: Env, db: Session, kind: str, reporter: int) -> tuple[str, str]:
    """What is reported: a message or a room that exists, else a person (never the reporter)."""
    tables = set(inspect(db.get_bind()).get_table_names())
    if kind == "message" and "messages" in tables:
        from api.chat.models import Message
        found = db.scalar(select(Message.id).where(Message.deleted_at.is_(None), Message.user_id != reporter).order_by(Message.id.desc()).limit(1))
        if found is not None:
            return "message", str(found)
    if kind == "room" and "rooms" in tables:
        from api.chat.models import Room
        found = db.scalar(select(Room.slug).where(Room.state == "open").order_by(Room.id.desc()).limit(1))
        if found is not None:
            return "room", found
    return "user", str(env.cast.take(exclude={reporter}).id)


def provider_seed_other(name: str):
    from api.ai.provider import DummyProvider, get_provider

    return DummyProvider() if name == "dummy" else get_provider()


