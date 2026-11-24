"""The current time in UTC, the one clock the models and services use."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    """The moment with its time zone: a naive one (SQLite keeps none) is taken as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
