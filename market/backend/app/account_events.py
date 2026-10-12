"""Reactions to account events published by `center` (delivered at least once).

Data model: `products` (seller_id, seller_name), `cart_items` (user_id),
`orders` (buyer_id, buyer_name), `order_items` (seller_id), `reviews`
(user_id, username), `idempotency_records` (user_id).

Deletion:
- DELETED: the user's cart items and checkout idempotency records (purely
  personal, nobody else relies on them).
- ANONYMIZED, rows kept: orders bought by the user (the sellers still need
  them): buyer_id -> tombstone 0, buyer_name -> DELETED_USERNAME; the user's
  reviews (other shoppers read them): user_id -> -user_id (an opaque per-user
  tombstone, because (product_id, user_id) is unique and several deleted users
  may have reviewed the same product), username -> DELETED_USERNAME;
  order lines sold by the user: seller_id -> 0.
- Products sold by the user are anonymized (seller_id 0, seller_name replaced)
  AND deactivated with stock 0: orders, carts and reviews reference them, so
  deleting is not clearly safe, but nobody can fulfil them any more.
Center ids are positive, so 0 and negative ids never match a live user.

Rename updates products.seller_name, orders.buyer_name and reviews.username.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.models import CartItem, IdempotencyRecord, Order, OrderItem, Product, Review

DELETED_USERNAME = "Người dùng đã xóa"
DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(delete(CartItem).where(CartItem.user_id == user_id))
    db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id))
    db.execute(
        update(Order)
        .where(Order.buyer_id == user_id)
        .values(buyer_id=DELETED_USER_ID, buyer_name=DELETED_USERNAME)
    )
    db.execute(
        update(Review)
        .where(Review.user_id == user_id)
        .values(user_id=-user_id, username=DELETED_USERNAME)
    )
    db.execute(update(OrderItem).where(OrderItem.seller_id == user_id).values(seller_id=DELETED_USER_ID))
    db.execute(
        update(Product)
        .where(Product.seller_id == user_id)
        .values(seller_id=DELETED_USER_ID, seller_name=DELETED_USERNAME, is_active=False, stock=0)
    )


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    if user_id == DELETED_USER_ID:
        return
    db.execute(update(Product).where(Product.seller_id == user_id).values(seller_name=new_username))
    db.execute(update(Order).where(Order.buyer_id == user_id).values(buyer_name=new_username))
    db.execute(update(Review).where(Review.user_id == user_id).values(username=new_username))
