"""Order business logic: checkout, payment, status changes. Raises HTTPException."""

from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.market.constants import (
    BUYER_TARGETS,
    ORDER_FLOW,
    MAX_OPEN_PENDING_ORDERS,
    SELLER_TARGETS,
    STATUS_CANCELLED,
    STATUS_DELIVERED,
    STATUS_PAID,
    STATUS_PENDING,
    STATUS_RETURN_REQUESTED,
    STATUS_RETURNED,
    RETURN_TARGETS,
    RETURN_WINDOW_DAYS,
)
from api.market.models import CartItem, DiscountCode, Order, Product, seller_ids_text, utcnow
from api.market.payments import PaymentError, PaymentProvider
from api.market.schemas import OrderItemOut, OrderOut
from sn_shared import directory
from sn_shared.security import TokenPayload
from sn_shared.clock import aware

def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def order_views(db: Session, orders: list[Order], viewer_id: int) -> list[OrderOut]:
    """Views of many orders with the buyer names read once."""
    found = directory.names(db, [order.buyer_id for order in orders])
    return [order_view(order, viewer_id, found[order.buyer_id]) for order in orders]


def order_view(order: Order, viewer_id: int, buyer_username: str) -> OrderOut:
    """The buyer sees every line; a seller sees only their own lines and subtotal."""
    lines = order.items if order.buyer_id == viewer_id else [
        item for item in order.items if item["seller_id"] == viewer_id
    ]
    items = [
        OrderItemOut(
            product_id=item["product_id"],
            name=item["name"],
            unit_price_cents=item["unit_price_cents"],
            quantity=item["quantity"],
            line_total_cents=item["unit_price_cents"] * item["quantity"] - item.get("discount_cents", 0),
            discount_cents=item.get("discount_cents", 0),
        )
        for item in lines
    ]
    return OrderOut(
        id=order.id,
        status=order.status,  # type: ignore[arg-type]
        currency=order.currency,
        total_cents=sum(item.line_total_cents for item in items),
        buyer_username=buyer_username,
        created_at=order.created_at,
        items=items,
        discount_code=order.discount_code if items and any(item.discount_cents for item in items) else None,
        discount_cents=sum(item.discount_cents for item in items),
        delivered_at=order.delivered_at,
    )


def involved_order(db: Session, order_id: int, user_id: int) -> Order:
    """The order if the user is its buyer or a seller on it; otherwise 404 (no leak)."""
    order = db.get(Order, order_id)
    if order is None or not (
        order.buyer_id == user_id or any(item["seller_id"] == user_id for item in order.items)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _checkout_replay(db: Session, user_id: int, key: str | None) -> Order | None:
    if key is None:
        return None
    return db.scalar(select(Order).where(Order.buyer_id == user_id, Order.idempotency_key == key))


def _claim_cart(db: Session, user_id: int) -> list[tuple[CartItem, Product]]:
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.user_id == user_id, Product.is_active.is_(True))
        .order_by(Product.id)  # stable lock order avoids deadlocks between buyers
    ).all()
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your cart is empty")
    if any(product.seller_id == user_id for _, product in rows):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot buy your own product")
    # Deleting the exact lines read makes a concurrent second checkout of the same
    # cart match fewer rows and fail, so one cart can never become two orders.
    deleted = db.execute(
        delete(CartItem).where(CartItem.id.in_([item.id for item, _ in rows]))
    )
    if deleted.rowcount != len(rows):
        raise conflict("Your cart changed, please review it and try again")
    return [(item, product) for item, product in rows]


def _reserve_stock(db: Session, item: CartItem, product: Product) -> None:
    """Atomic conditional decrement: never oversells, never goes negative."""
    result = db.execute(
        update(Product)
        .where(
            Product.id == product.id,
            Product.is_active.is_(True),
            Product.stock >= item.quantity,
            Product.price_cents == product.price_cents,  # price must not change mid-checkout
        )
        .values(stock=Product.stock - item.quantity)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise conflict(f"'{product.name}' is out of stock or its price changed")


def _apply_code(db: Session, code: str, items: list[dict]) -> str:
    """Take one use of the code and write the discount into the lines of its seller. Returns the code as stored."""
    found = db.scalar(select(DiscountCode).where(func.upper(DiscountCode.code) == code.upper()))
    if found is None or not found.is_active or (found.expires_at is not None and aware(found.expires_at) <= utcnow()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This discount code is not valid")
    lines = [item for item in items if item["seller_id"] == found.seller_id]
    if not lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This discount code is for products that are not in your cart")
    taken = db.execute(  # atomic: two orders cannot take the last use
        update(DiscountCode)
        .where(DiscountCode.id == found.id, (DiscountCode.max_uses == 0) | (DiscountCode.used < DiscountCode.max_uses))
        .values(used=DiscountCode.used + 1)
        .execution_options(synchronize_session=False)
    )
    if taken.rowcount != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This discount code has no uses left")
    for item in lines:
        item["discount_cents"] = item["unit_price_cents"] * item["quantity"] * found.percent // 100
    return found.code


def _release_code(db: Session, order: Order) -> None:
    """A cancelled or returned order gives back the use of its code."""
    if order.discount_code:
        db.execute(
            update(DiscountCode)
            .where(func.upper(DiscountCode.code) == order.discount_code.upper(), DiscountCode.used > 0)
            .values(used=DiscountCode.used - 1)
            .execution_options(synchronize_session=False)
        )


def checkout(db: Session, user: TokenPayload, key: str | None, code: str | None = None) -> tuple[Order, bool]:
    """Create an order from the cart. Returns (order, created); created is False on replay."""
    replay = _checkout_replay(db, user.user_id, key)
    if replay is not None:
        return replay, False
    open_orders = db.scalar(
        select(func.count(Order.id)).where(
            Order.buyer_id == user.user_id, Order.status == STATUS_PENDING
        )
    )
    if (open_orders or 0) >= MAX_OPEN_PENDING_ORDERS:
        raise conflict("Too many unpaid orders, pay or cancel one first")
    lines = _claim_cart(db, user.user_id)
    items = [
        {
            "product_id": product.id,
            "seller_id": product.seller_id,
            "name": product.name,
            "unit_price_cents": product.price_cents,
            "quantity": item.quantity,
        }
        for item, product in lines
    ]
    applied = _apply_code(db, code, items) if code else None
    discount = sum(item.get("discount_cents", 0) for item in items)
    order = Order(
        buyer_id=user.user_id,
        status=STATUS_PENDING,
        discount_code=applied,
        discount_cents=discount,
        total_cents=sum(product.price_cents * item.quantity for item, product in lines) - discount,
        items=items,
        seller_ids=seller_ids_text(items),
        idempotency_key=key,
    )
    try:
        db.add(order)
        db.flush()
        for item, product in lines:
            _reserve_stock(db, item, product)
        db.commit()
    except IntegrityError:  # same key raced in from another request
        db.rollback()
        replay = _checkout_replay(db, user.user_id, key)
        if replay is None:
            raise
        return replay, False
    return order, True


def pay(
    db: Session, user: TokenPayload, order_id: int, provider: PaymentProvider, key: str | None
) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.buyer_id != user.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if key is not None and order.pay_key == key:
        return order
    # Claim first (atomic status flip) so two concurrent pay calls cannot both charge.
    claimed = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == STATUS_PENDING)
        .values(status=STATUS_PAID)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        raise conflict("Order is not awaiting payment")
    try:
        result = provider.charge(order.id, order.total_cents, order.currency)
    except PaymentError:
        db.rollback()  # undoes the claim
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Payment failed") from None
    db.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(payment_reference=result.reference, pay_key=key)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.refresh(order)
    return order


def _role_targets(order: Order, user_id: int) -> frozenset[str]:
    if order.buyer_id == user_id:
        return BUYER_TARGETS
    if order.status == STATUS_RETURN_REQUESTED:
        return RETURN_TARGETS
    return SELLER_TARGETS  # involved_order already proved the user is a seller on it


def _restock(db: Session, order: Order) -> None:
    _release_code(db, order)
    for item in order.items:  # restock exactly what checkout took
        db.execute(
            update(Product)
            .where(Product.id == item["product_id"])
            .values(stock=Product.stock + item["quantity"])
            .execution_options(synchronize_session=False)
        )


def _refund_or_rollback(db: Session, order: Order, provider: PaymentProvider) -> None:
    """Refund a paid order; on failure undo the whole cancellation (status and stock)."""
    try:
        if order.payment_reference is None:
            raise PaymentError("missing payment reference")
        provider.refund(order.payment_reference)
    except PaymentError:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Refund failed, order unchanged") from None


def expire_stale_orders(db: Session, now: datetime, ttl: timedelta) -> int:
    """Cancel pending orders older than ttl and restore their stock, atomically per order.

    Called lazily from request paths (no background worker). Returns how many expired.
    """
    stale = db.scalars(
        select(Order).where(Order.status == STATUS_PENDING, Order.created_at < now - ttl)
    ).all()
    expired = 0
    for order in stale:
        claimed = db.execute(
            update(Order)
            .where(Order.id == order.id, Order.status == STATUS_PENDING)
            .values(status=STATUS_CANCELLED)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount == 1:  # lost races mean someone else paid or cancelled it
            _restock(db, order)
            expired += 1
    if stale:
        db.commit()
    return expired


def change_status(
    db: Session, user: TokenPayload, order_id: int, target: str, provider: PaymentProvider
) -> Order:
    """Sellers may only ship (paid -> shipped); only the buyer cancels or confirms delivery.

    A multi-seller order has a single shared status, not one per seller.
    """
    order = involved_order(db, order_id, user.user_id)
    if target not in _role_targets(order, user.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may not set that status")
    ORDER_FLOW.check(order.status, target, "an order")
    current = order.status
    values: dict = {"status": target}
    if target == STATUS_DELIVERED and current != STATUS_RETURN_REQUESTED:
        values["delivered_at"] = utcnow()
    if target == STATUS_RETURN_REQUESTED:
        if utcnow() - aware(order.delivered_at or order.created_at) > timedelta(days=RETURN_WINDOW_DAYS):
            raise conflict(f"A return must be asked within {RETURN_WINDOW_DAYS} days of the delivery")
    changed = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == current)  # guards against races
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise conflict("Order was changed by someone else, please reload")
    if target == STATUS_CANCELLED:
        _restock(db, order)
        if current == STATUS_PAID:
            _refund_or_rollback(db, order, provider)
    if target == STATUS_RETURNED:  # the seller accepted the return: the money goes back and the goods return to the stock
        _restock(db, order)
        _refund_or_rollback(db, order, provider)
    db.commit()
    db.refresh(order)
    return order
