"""Reactions to account events published by `center` (delivered at least once).

Data model: `products` (seller_id, seller_username), `cart_items` (user_id),
`orders` (buyer_id, idempotency_key, pay_key, items with seller_id, seller_ids), the reviews (`comments` of `sn_shared`, kind `product`)
(user_id, username).

Deletion:
- DELETED: the user's cart items; the idempotency keys of their orders are cleared
  (purely personal, nobody else relies on them).
- ANONYMIZED, rows kept: orders bought by the user (the sellers still need
  them): buyer_id -> tombstone 0, buyer_username -> DELETED_USERNAME; the user's
  reviews (other shoppers read them): user_id -> -user_id (an opaque per-user
  tombstone, because (product_id, user_id) is unique and several deleted users
  may have reviewed the same product), username -> DELETED_USERNAME;
  order lines sold by the user: seller_id -> 0 (in `orders.items`, and out of `orders.seller_ids`).
- Products sold by the user are anonymized (seller_id 0, seller_username replaced)
  AND deactivated with stock 0: orders, carts and reviews reference them, so
  deleting is not clearly safe, but nobody can fulfil them any more.
Center ids are positive, so 0 and negative ids never match a live user.

Rename updates products.seller_username, orders.buyer_username and the name on its reviews.

Both handlers are idempotent, never raise for missing data and never commit.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from sn_shared import comments

from api.market.models import CartItem, Order, Product, seller_ids_text

import logging
logger = logging.getLogger(__name__)

DELETED_USER_ID = 0


def on_user_deleted(db: Session, user_id: int) -> None:
    try:
        if user_id == DELETED_USER_ID:
            return
        db.execute(delete(CartItem).where(CartItem.user_id == user_id))
        db.execute(
            update(Order)
            .where(Order.buyer_id == user_id)
            .values(buyer_id=DELETED_USER_ID, idempotency_key=None, pay_key=None)
        )
        comments.anonymize_user(db, user_id, ["product"])  # the reviews stay for the other shoppers
        anonymize_seller_lines(db, user_id)
        db.execute(
            update(Product)
            .where(Product.seller_id == user_id)
            .values(seller_id=DELETED_USER_ID, is_active=False, stock=0)
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("on_user_deleted failed")
        raise


def anonymize_seller_lines(db: Session, user_id: int) -> None:
    try:
        for order in db.scalars(select(Order).where(Order.seller_ids.like(f"%|{user_id}|%"))):
            items = [
                {**item, "seller_id": DELETED_USER_ID} if item["seller_id"] == user_id else item
                for item in order.items
            ]
            order.items = items  # a new list: in-place changes of a JSON column are not noticed
            order.seller_ids = seller_ids_text(items)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("anonymize_seller_lines failed")
        raise


def on_user_renamed(db: Session, user_id: int, new_username: str) -> None:
    """Nothing to do: names are read from `users` (sn_shared.directory), no table keeps a copy."""
