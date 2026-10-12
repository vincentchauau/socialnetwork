from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import PAGE_DEFAULT_LIMIT, PAGE_MAX_LIMIT, STATUS_DELIVERED
from app.deps import get_db
from app.models import Order, OrderItem, Product, Review
from app.schemas import ReviewIn, ReviewOut
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

ProductId = Annotated[int, Path(ge=1)]


def _active_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


def _has_delivered_purchase(db: Session, user_id: int, product_id: int) -> bool:
    found = db.scalar(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.buyer_id == user_id,
            Order.status == STATUS_DELIVERED,
            OrderItem.product_id == product_id,
        )
        .limit(1)
    )
    return found is not None


@router.post(
    "/products/{product_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
def create_review(
    product_id: ProductId,
    body: ReviewIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Review:
    _active_product(db, product_id)
    if not _has_delivered_purchase(db, user.user_id, product_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only buyers with a delivered order can review")
    already = db.scalar(
        select(Review.id).where(Review.product_id == product_id, Review.user_id == user.user_id)
    )
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already reviewed this product")
    review = Review(
        product_id=product_id,
        user_id=user.user_id,
        username=user.username,
        rating=body.rating,
        text=body.text,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError:  # concurrent duplicate caught by the unique constraint
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already reviewed this product") from None
    return review


@router.get("/products/{product_id}/reviews", response_model=list[ReviewOut])
def list_reviews(
    product_id: ProductId,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX_LIMIT)] = PAGE_DEFAULT_LIMIT,
    _user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Review]:
    _active_product(db, product_id)
    query = select(Review).where(Review.product_id == product_id)
    if cursor is not None:
        query = query.where(Review.id < cursor)
    return list(db.scalars(query.order_by(Review.id.desc()).limit(limit)).all())
