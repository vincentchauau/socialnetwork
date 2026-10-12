"""Shared limits and enumerations. Money is always integer minor units (cents)."""

CURRENCY = "USD"  # ISO 4217; every price in this service is in this currency's minor unit

MAX_PRICE_CENTS = 1_000_000_000
MAX_STOCK = 1_000_000
MAX_CART_QUANTITY = 99
NAME_MAX = 120
DESCRIPTION_MAX = 4000
IMAGE_URL_MAX = 500
CATEGORY_MAX = 40
DEFAULT_CATEGORY = "other"
USERNAME_MAX = 64
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

# current status -> statuses it may move to
TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PENDING: frozenset({STATUS_PAID, STATUS_CANCELLED}),
    STATUS_PAID: frozenset({STATUS_SHIPPED, STATUS_CANCELLED}),
    STATUS_SHIPPED: frozenset({STATUS_DELIVERED}),
    STATUS_DELIVERED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}
# who may request which target status through PATCH /orders/{id}/status.
# An order has ONE shared status even when it contains items from several sellers:
# any involved seller may mark it shipped (paid -> shipped), and only the buyer can
# confirm delivery, so no seller can unlock reviews for the whole order.
BUYER_TARGETS = frozenset({STATUS_CANCELLED, STATUS_DELIVERED})
SELLER_TARGETS = frozenset({STATUS_SHIPPED})

# Unpaid orders hold stock, so they expire and each buyer may hold only a few.
DEFAULT_ORDER_TTL_MINUTES = 15
MAX_OPEN_PENDING_ORDERS = 5
MAX_CART_PRODUCTS = 50
