from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.market.constants import (
    CURRENCY,
    CATEGORY_MAX,
    DEFAULT_CATEGORY,
    IDEMPOTENCY_KEY_MAX,
    IMAGE_URL_MAX,
    NAME_MAX,
)
from api.market.db import Base
from sn_shared.clock import utcnow

import logging
logger = logging.getLogger(__name__)

STATUS_COLUMN_LENGTH = 20
REFERENCE_COLUMN_LENGTH = 64


def seller_ids_text(items: list[dict]) -> str:
    """The sellers of an order as `|3|9|` (what `Order.seller_ids` holds), so a seller's orders are found with a plain LIKE."""
    try:
        ids = sorted({int(item["seller_id"]) for item in items if int(item["seller_id"]) > 0})
        return f"|{'|'.join(str(seller_id) for seller_id in ids)}|" if ids else ""
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("seller_ids_text failed")
        raise


class Product(Base):
    __tablename__ = "market_products"
    __table_args__ = (Index("ix_products_seller", "seller_id"), Index("ix_products_category", "category"))

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(BigInteger)
    stock: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String(IMAGE_URL_MAX), nullable=True)
    category: Mapped[str] = mapped_column(String(CATEGORY_MAX), default=DEFAULT_CATEGORY)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("market_products.id"))
    quantity: Mapped[int] = mapped_column(Integer)


class Order(Base):
    """An order. `items` is the snapshot taken at purchase time: [{product_id, seller_id, name, unit_price_cents, quantity}].

    `idempotency_key` is the Idempotency-Key of the checkout that made it, `pay_key` the one of its payment.
    """

    __tablename__ = "market_orders"
    __table_args__ = (
        Index("ix_orders_buyer_id", "buyer_id", "id"),
        Index("uq_orders_buyer_idempotency", "buyer_id", "idempotency_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(STATUS_COLUMN_LENGTH))
    total_cents: Mapped[int] = mapped_column(BigInteger)
    payment_reference: Mapped[str | None] = mapped_column(
        String(REFERENCE_COLUMN_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list] = mapped_column(JSON, default=list, server_default=text("'[]'"))
    seller_ids: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))  # `|3|9|` (see `seller_ids_text`)
    idempotency_key: Mapped[str | None] = mapped_column(String(IDEMPOTENCY_KEY_MAX), nullable=True)
    pay_key: Mapped[str | None] = mapped_column(String(IDEMPOTENCY_KEY_MAX), nullable=True)
    discount_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def currency(self) -> str:
        try:
            return CURRENCY
        except Exception as error:
            if getattr(error, "status_code", None) is None:
                logger.exception("currency failed")
            raise
