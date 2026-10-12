from typing import Annotated

from fastapi import Header, Request

from app.constants import IDEMPOTENCY_KEY_MAX, IDEMPOTENCY_KEY_PATTERN
from app.db import get_db
from app.payments import PaymentProvider

__all__ = ["IdempotencyKey", "get_db", "get_payment_provider"]

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
