"""Starting and stopping center's account-event consumer, the same way for every app."""

import inspect
import os
from typing import Any

from sqlalchemy.orm import sessionmaker

import logging
logger = logging.getLogger(__name__)


def start_consumer(app: str, session_factory: sessionmaker) -> Any:
    """Start center's account-event consumer for `app`; None in tests, without Redis or without the library."""
    if os.environ.get("TESTING") or not os.environ.get("REDIS_URL"):
        return None
    try:
        from sn_shared.events import start_account_consumer
    except ImportError:
        return None
    return start_account_consumer(app, session_factory, handlers_module=f"api.{app}.account_events")


async def stop_consumer(handle: Any) -> None:
    try:
        stop = getattr(handle, "stop", None) or getattr(handle, "close", None)
        if stop is None:
            return
        result = stop()
        if inspect.isawaitable(result):
            await result
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("stop_consumer failed")
        raise
