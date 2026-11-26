"""The reviews of a product: comments (`sn_shared.comments`) with a rating of 1 to 5, given once by a buyer whose order was delivered."""

from fastapi import HTTPException, status
from sn_shared import comments
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.market.constants import PAGE_DEFAULT_LIMIT, PAGE_MAX_LIMIT, REVIEW_TEXT_MAX, STATUS_DELIVERED
from api.market.models import Order, Product


def active_product(db: Session, product_id: int, _user=None) -> Product:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


def has_delivered_purchase(db: Session, user_id: int, product_id: int) -> bool:
    delivered = db.scalars(
        select(Order.items).where(Order.buyer_id == user_id, Order.status == STATUS_DELIVERED)
    )
    return any(item["product_id"] == product_id for items in delivered for item in items)


def must_have_bought(db: Session, product: Product, user) -> None:
    if not has_delivered_purchase(db, user.user_id, product.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only buyers with a delivered order can review")


PRODUCT_REVIEWS = comments.CommentKind(
    "product", "/products/{object_id}/reviews", "/reviews/{comment_id}",
    visible=active_product, rating="required", once=True, content_max=REVIEW_TEXT_MAX,
    page_default=PAGE_DEFAULT_LIMIT, page_max=PAGE_MAX_LIMIT, newest_first=True,
    may_write=must_have_bought, others_are_hidden=True, strict_body=True, tag="reviews",
)
router = comments.comments_router(PRODUCT_REVIEWS)
