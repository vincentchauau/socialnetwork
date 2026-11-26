"""Payment stub. No card data is ever collected, stored or logged by this service."""

import secrets
from dataclasses import dataclass
from typing import Protocol

import logging
logger = logging.getLogger(__name__)

REFERENCE_PREFIX = "fake_"
REFERENCE_BYTES = 12


class PaymentError(Exception):
    """The provider declined or could not process the charge."""


@dataclass(frozen=True)
class PaymentResult:
    reference: str


class PaymentProvider(Protocol):
    def charge(self, order_id: int, amount_cents: int, currency: str) -> PaymentResult:
        """Charge the full amount for an order or raise PaymentError."""
        ...

    def refund(self, reference: str) -> None:
        """Refund a previous charge in full or raise PaymentError."""
        ...


class FakePaymentProvider:
    """Always succeeds and returns a random reference. For development only."""

    def charge(self, order_id: int, amount_cents: int, currency: str) -> PaymentResult:
        try:
            return PaymentResult(reference=REFERENCE_PREFIX + secrets.token_hex(REFERENCE_BYTES))
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("charge failed")
            raise

    def refund(self, reference: str) -> None:
        try:
            return None
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("refund failed")
            raise
