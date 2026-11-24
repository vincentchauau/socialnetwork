from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from api.market.constants import (
    CATEGORY_MAX,
    DEFAULT_CATEGORY,
    DESCRIPTION_MAX,
    IMAGE_URL_MAX,
    MAX_CART_QUANTITY,
    MAX_PRICE_CENTS,
    MAX_STOCK,
    NAME_MAX,
    CODE_MAX,
)

ALLOWED_URL_SCHEMES = frozenset({"https"})
RATING_MIN = 1
RATING_MAX = 5
RATING_DECIMALS = 2

# strict ints: money and counts must be JSON integers (no 5.0, "5" or true)
Cents = Annotated[int, Field(strict=True, ge=1, le=MAX_PRICE_CENTS)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)]
Category = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=CATEGORY_MAX),
]
OrderStatus = Literal["pending_payment", "paid", "shipped", "delivered", "cancelled", "return_requested", "returned"]


def validate_http_url(value: str) -> str:
    """Only absolute https URLs with a host; no whitespace or control characters."""
    if any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("URL must not contain whitespace")
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError as error:
        raise ValueError("Invalid URL") from error
    if parts.scheme not in ALLOWED_URL_SCHEMES or not host:
        raise ValueError("URL must start with https://")
    return value


class ProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Annotated[str, StringConstraints(max_length=DESCRIPTION_MAX)] = ""
    price_cents: Cents
    stock: Annotated[int, Field(strict=True, ge=0, le=MAX_STOCK)]
    image_url: Annotated[str | None, Field(max_length=IMAGE_URL_MAX)] = None
    category: Category = DEFAULT_CATEGORY

    @field_validator("image_url")
    @classmethod
    def _check_image_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return validate_http_url(value)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    seller_username: str
    name: str
    description: str
    price_cents: int
    currency: str
    stock: int
    image_url: str | None
    category: str
    rating_average: float | None
    review_count: int
    created_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    next_cursor: int | None


class CartItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: Annotated[int, Field(strict=True, ge=0, le=MAX_CART_QUANTITY)]


class CartLineOut(BaseModel):
    product_id: int
    name: str
    image_url: str | None
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    stock: int


class CartOut(BaseModel):
    items: list[CartLineOut]
    currency: str
    item_count: int
    total_cents: int


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    discount_cents: int = 0


class OrderOut(BaseModel):
    id: int
    status: OrderStatus
    currency: str
    total_cents: int
    buyer_username: str
    created_at: datetime
    items: list[OrderItemOut]
    discount_code: str | None = None
    discount_cents: int = 0
    delivered_at: datetime | None = None


class OrderPage(BaseModel):
    items: list[OrderOut]
    next_cursor: int | None


class CheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=CODE_MAX)] = None


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OrderStatus


