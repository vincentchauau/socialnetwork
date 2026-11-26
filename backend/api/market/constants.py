"""Shared limits and enumerations. Money is always integer minor units (cents)."""

import os

from sn_shared.states import Transitions

CURRENCY = "USD"  # ISO 4217; every price in this service is in this currency's minor unit

MAX_PRICE_CENTS = 1_000_000_000
MAX_STOCK = 1_000_000
MAX_CART_QUANTITY = 99
NAME_MAX = 120
DESCRIPTION_MAX = 4000
IMAGE_URL_MAX = 500
CATEGORY_MAX = 40
DEFAULT_CATEGORY = "other"
SEARCH_MAX = 100
REVIEW_TEXT_MAX = 1000
IDEMPOTENCY_KEY_MAX = 128
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._:-]+$"

PAGE_DEFAULT_LIMIT = 20
PAGE_MAX_LIMIT = 50

STATUS_PENDING = "pending_payment"
STATUS_PAID = "paid"
STATUS_SHIPPED = "shipped"
STATUS_DELIVERED = "delivered"
STATUS_CANCELLED = "cancelled"
STATUS_RETURN_REQUESTED = "return_requested"
STATUS_RETURNED = "returned"

# current status -> statuses it may move to
ORDER_FLOW = Transitions({
    STATUS_PENDING: [STATUS_PAID, STATUS_CANCELLED],
    STATUS_PAID: [STATUS_SHIPPED, STATUS_CANCELLED],
    STATUS_SHIPPED: [STATUS_DELIVERED],
    STATUS_DELIVERED: [STATUS_RETURN_REQUESTED],
    STATUS_RETURN_REQUESTED: [STATUS_RETURNED, STATUS_DELIVERED],  # a seller accepts the return, or refuses it (back to delivered)
    STATUS_RETURNED: [],
    STATUS_CANCELLED: [],
})
# who may request which target status through PATCH /orders/{id}/status.
# An order has ONE shared status even when it contains items from several sellers:
# any involved seller may mark it shipped (paid -> shipped), and only the buyer can
# confirm delivery, so no seller can unlock reviews for the whole order.
BUYER_TARGETS = frozenset({STATUS_CANCELLED, STATUS_DELIVERED, STATUS_RETURN_REQUESTED})
SELLER_TARGETS = frozenset({STATUS_SHIPPED})
RETURN_TARGETS = frozenset({STATUS_RETURNED, STATUS_DELIVERED})  # what a seller may set on an order whose return was asked
RETURN_WINDOW_DAYS = 14  # a return is asked within this many days of the delivery

# One percent off every order (0 = none), read from the environment at start-up; checkout applies it to the whole order.
ORDER_DISCOUNT_PERCENT_MAX = 90
ORDER_DISCOUNT_PERCENT = int(os.environ.get("ORDER_DISCOUNT_PERCENT", "0"))
if not 0 <= ORDER_DISCOUNT_PERCENT <= ORDER_DISCOUNT_PERCENT_MAX:
    raise ValueError(f"ORDER_DISCOUNT_PERCENT must be between 0 and {ORDER_DISCOUNT_PERCENT_MAX}")

# Unpaid orders hold stock, so they expire and each buyer may hold only a few.
DEFAULT_ORDER_TTL_MINUTES = 15
MAX_OPEN_PENDING_ORDERS = 5
MAX_CART_PRODUCTS = 50
