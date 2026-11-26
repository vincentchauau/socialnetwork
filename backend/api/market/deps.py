from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from api.market import order_service
from api.market.constants import IDEMPOTENCY_KEY_MAX, IDEMPOTENCY_KEY_PATTERN
from api.market.db import get_db
from api.market.payments import PaymentProvider

import logging
logger = logging.getLogger(__name__)

__all__ = ["IdempotencyKey", "expire_stale", "get_db", "get_payment_provider"]

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=IDEMPOTENCY_KEY_MAX,
        pattern=IDEMPOTENCY_KEY_PATTERN,
    ),
]


def get_payment_provider(request: Request) -> PaymentProvider:
    try:
        return request.app.state.payment_provider
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_payment_provider failed")
        raise


def expire_stale(request: Request, db: Session = Depends(get_db)) -> None:
    """Lazy expiry of unpaid orders; attach with dependencies=[Depends(expire_stale)]."""
    try:
        state = request.app.state
        order_service.expire_stale_orders(db, state.clock(), state.order_ttl)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("expire_stale failed")
        raise
