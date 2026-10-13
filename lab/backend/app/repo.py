"""lab_events persistence. Plain synchronous functions: routes call them through the threadpool, the worker
through asyncio.to_thread. Each call uses its own short session and commits."""

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import KIND_LOG, KIND_NOTIFICATION, LabEvent
from app.schemas import LogOut, NotificationOut

STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_RETRYING = "retrying"
STATUS_DONE = "done"
STATUS_DEAD = "dead"
_FINISHED = (STATUS_DONE, STATUS_DEAD)


def create_notification(factory: sessionmaker, user_id: int, title: str, body: str) -> int:
    with factory() as db:
        row = LabEvent(
            user_id=user_id, kind=KIND_NOTIFICATION, title=title, body=body, status=STATUS_QUEUED, attempts=0
        )
        db.add(row)
        db.commit()
        return row.id


def remove_event(factory: sessionmaker, event_id: int) -> None:
    with factory() as db:
        db.execute(delete(LabEvent).where(LabEvent.id == event_id))
        db.commit()


def delete_user_events(factory: sessionmaker, user_id: int) -> None:
    with factory() as db:
        db.execute(delete(LabEvent).where(LabEvent.user_id == user_id))
        db.commit()


def list_notifications(factory: sessionmaker, user_id: int, limit: int) -> list[dict]:
    with factory() as db:
        rows = db.scalars(_newest(user_id, KIND_NOTIFICATION, limit)).all()
        return [NotificationOut.model_validate(r).model_dump(by_alias=True, mode="json") for r in rows]


def list_logs(factory: sessionmaker, user_id: int, limit: int) -> list[dict]:
    with factory() as db:
        rows = db.scalars(_newest(user_id, KIND_LOG, limit)).all()
        return [LogOut.model_validate(r).model_dump(by_alias=True, mode="json") for r in rows]


def _newest(user_id: int, kind: str, limit: int):
    return (
        select(LabEvent)
        .where(LabEvent.user_id == user_id, LabEvent.kind == kind)
        .order_by(LabEvent.id.desc())
        .limit(limit)
    )


def get_notification_title(factory: sessionmaker, event_id: int) -> str | None:
    with factory() as db:
        row = db.get(LabEvent, event_id)
        return row.title if row is not None and row.kind == KIND_NOTIFICATION else None


def set_notification_status(factory: sessionmaker, event_id: int, status: str, attempts: int) -> bool:
    """False when the row is gone (the user cleared their events meanwhile)."""
    values: dict = {"status": status, "attempts": attempts}
    if status in _FINISHED:
        values["processed_at"] = datetime.now(timezone.utc)
    with factory() as db:
        result = db.execute(
            update(LabEvent).where(LabEvent.id == event_id, LabEvent.kind == KIND_NOTIFICATION).values(**values)
        )
        db.commit()
        return result.rowcount > 0


def store_log(
    factory: sessionmaker, user_id: int, level: str, message: str, partition: int, offset: int, created_at: datetime
) -> bool:
    """Insert one consumed Kafka message; False when (partition, offset) is already stored (redelivery)."""
    with factory() as db:
        if _log_exists(db, partition, offset):
            return False
        db.add(
            LabEvent(
                user_id=user_id, kind=KIND_LOG, title=level, body=message, kafka_partition=partition,
                kafka_offset=offset, created_at=created_at, processed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return True


def _log_exists(db: Session, partition: int, offset: int) -> bool:
    return (
        db.scalar(
            select(LabEvent.id).where(
                LabEvent.kind == KIND_LOG, LabEvent.kafka_partition == partition, LabEvent.kafka_offset == offset
            )
        )
        is not None
    )
