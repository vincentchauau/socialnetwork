from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app import order_service
from app.constants import IDEMPOTENCY_KEY_MAX, IDEMPOTENCY_KEY_PATTERN
from app.db import get_db
from app.payments import PaymentProvider

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
    return request.app.state.payment_provider


def expire_stale(request: Request, db: Session = Depends(get_db)) -> None:
    """Lazy expiry of unpaid orders; attach with dependencies=[Depends(expire_stale)]."""
    state = request.app.state
    order_service.expire_stale_orders(db, state.clock(), state.order_ttl)
