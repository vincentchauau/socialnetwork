from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import (
    CATEGORY_MAX,
    DEFAULT_CATEGORY,
    IDEMPOTENCY_KEY_MAX,
    IMAGE_URL_MAX,
    NAME_MAX,
    USERNAME_MAX,
)
from app.db import Base

STATUS_COLUMN_LENGTH = 20
SCOPE_COLUMN_LENGTH = 64
CURRENCY_COLUMN_LENGTH = 3
REFERENCE_COLUMN_LENGTH = 64


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_seller", "seller_id"), Index("ix_products_category", "category"))

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(Integer)
    seller_name: Mapped[str] = mapped_column(String(USERNAME_MAX))
    name: Mapped[str] = mapped_column(String(NAME_MAX))
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(BigInteger)
    stock: Mapped[int] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String(IMAGE_URL_MAX), nullable=True)
    category: Mapped[str] = mapped_column(String(CATEGORY_MAX), default=DEFAULT_CATEGORY)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_buyer_id", "buyer_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(Integer)
    buyer_name: Mapped[str] = mapped_column(String(USERNAME_MAX))
    status: Mapped[str] = mapped_column(String(STATUS_COLUMN_LENGTH))
    currency: Mapped[str] = mapped_column(String(CURRENCY_COLUMN_LENGTH))
    total_cents: Mapped[int] = mapped_column(BigInteger)
    payment_reference: Mapped[str | None] = mapped_column(
        String(REFERENCE_COLUMN_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list["OrderItem"]] = relationship(
        lazy="selectin", order_by="OrderItem.id", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_seller", "seller_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    seller_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(NAME_MAX))  # snapshot at purchase time
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)  # snapshot at purchase time
    quantity: Mapped[int] = mapped_column(Integer)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("product_id", "user_id", name="uq_review_product_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    username: Mapped[str] = mapped_column(String(USERNAME_MAX))
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "scope", "key", name="uq_idempotency"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(SCOPE_COLUMN_LENGTH))
    key: Mapped[str] = mapped_column(String(IDEMPOTENCY_KEY_MAX))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
