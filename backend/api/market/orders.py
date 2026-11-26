from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from api.market import order_service
from api.market.constants import PAGE_DEFAULT_LIMIT, PAGE_MAX_LIMIT
from api.market.deps import IdempotencyKey, expire_stale, get_db, get_payment_provider
from api.market.constants import STATUS_CANCELLED
from api.market.models import Order
from api.market.payments import PaymentProvider
from api.market.schemas import OrderOut, OrderPage, StatusIn
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
        items=order_service.order_views(db, page, user_id),
        next_cursor=page[-1].id if len(orders) > limit else None,
    )


@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(expire_stale)],
)
def create_order(
    response: Response,
    idempotency_key: IdempotencyKey = None,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    order, created = order_service.checkout(db, user, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
    return order_service.order_views(db, [order], user.user_id)[0]


@router.get("/orders", response_model=OrderPage, dependencies=[Depends(expire_stale)])
def list_orders(
    cursor: Cursor = None,
    limit: Limit = PAGE_DEFAULT_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPage:
    return _order_page(db, select(Order).where(Order.buyer_id == user.user_id), user.user_id, cursor, limit)


@router.get("/sales", response_model=OrderPage, dependencies=[Depends(expire_stale)])
def list_sales(
    cursor: Cursor = None,
    limit: Limit = PAGE_DEFAULT_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPage:
    mine = Order.seller_ids.like(f"%|{user.user_id}|%")
    return _order_page(db, select(Order).where(mine), user.user_id, cursor, limit)


@router.get("/orders/{order_id}", response_model=OrderOut, dependencies=[Depends(expire_stale)])
def get_order(
    order_id: OrderId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    order = order_service.involved_order(db, order_id, user.user_id)
    return order_service.order_views(db, [order], user.user_id)[0]


@router.post(
    "/orders/{order_id}/pay", response_model=OrderOut, dependencies=[Depends(expire_stale)]
)
def pay_order(
    order_id: OrderId,
    idempotency_key: IdempotencyKey = None,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
) -> OrderOut:
    order = order_service.pay(db, user, order_id, provider, idempotency_key)
    return order_service.order_views(db, [order], user.user_id)[0]


@router.patch(
    "/orders/{order_id}/status", response_model=OrderOut, dependencies=[Depends(expire_stale)]
)
def update_order_status(
    order_id: OrderId,
    body: StatusIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
) -> OrderOut:
    order = order_service.change_status(db, user, order_id, body.status, provider)
    return order_service.order_views(db, [order], user.user_id)[0]


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(expire_stale)])
def delete_order(
    order_id: OrderId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """The buyer removes an order that was cancelled from the list. Any other order is a record of a sale and stays."""
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != user.user_id:  # someone else's order looks like none
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.status != STATUS_CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a cancelled order can be deleted")
    db.delete(order)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
