from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app import order_service
from app.constants import PAGE_DEFAULT_LIMIT, PAGE_MAX_LIMIT
from app.deps import IdempotencyKey, get_db, get_payment_provider
from app.models import Order, OrderItem
from app.payments import PaymentProvider
from app.schemas import OrderOut, OrderPage, StatusIn
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

OrderId = Annotated[int, Path(ge=1)]
Cursor = Annotated[int | None, Query(ge=1)]
Limit = Annotated[int, Query(ge=1, le=PAGE_MAX_LIMIT)]


def _order_page(db: Session, query: Select[Any], user_id: int, cursor: int | None, limit: int) -> OrderPage:
    if cursor is not None:
        query = query.where(Order.id < cursor)
    orders = list(db.scalars(query.order_by(Order.id.desc()).limit(limit + 1)).all())
    page = orders[:limit]
    return OrderPage(
        items=[order_service.order_view(order, user_id) for order in page],
        next_cursor=page[-1].id if len(orders) > limit else None,
    )


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    response: Response,
    idempotency_key: IdempotencyKey = None,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    order, created = order_service.checkout(db, user, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return order_service.order_view(order, user.user_id)


@router.get("/orders", response_model=OrderPage)
def list_orders(
    cursor: Cursor = None,
    limit: Limit = PAGE_DEFAULT_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPage:
    return _order_page(db, select(Order).where(Order.buyer_id == user.user_id), user.user_id, cursor, limit)


@router.get("/sales", response_model=OrderPage)
def list_sales(
    cursor: Cursor = None,
    limit: Limit = PAGE_DEFAULT_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPage:
    sold = select(OrderItem.order_id).where(OrderItem.seller_id == user.user_id)
    return _order_page(db, select(Order).where(Order.id.in_(sold)), user.user_id, cursor, limit)


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: OrderId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    order = order_service.involved_order(db, order_id, user.user_id)
    return order_service.order_view(order, user.user_id)


@router.post("/orders/{order_id}/pay", response_model=OrderOut)
def pay_order(
    order_id: OrderId,
    idempotency_key: IdempotencyKey = None,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
) -> OrderOut:
    order = order_service.pay(db, user, order_id, provider, idempotency_key)
    return order_service.order_view(order, user.user_id)


@router.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: OrderId,
    body: StatusIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    order = order_service.change_status(db, user, order_id, body.status)
    return order_service.order_view(order, user.user_id)
