"""The current time in UTC, the one clock the models and services use."""

from datetime import datetime, timezone

import logging
logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    try:
        return datetime.now(timezone.utc)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("utcnow failed")
        raise


def aware(value: datetime) -> datetime:
    """The moment with its time zone: a naive one (SQLite keeps none) is taken as UTC."""
    try:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("aware failed")
        raise
