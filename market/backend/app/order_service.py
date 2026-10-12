"""Order business logic: checkout, payment, status changes. Raises HTTPException."""

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants import (
    BUYER_TARGETS,
    CURRENCY,
    SELLER_TARGETS,
    STATUS_CANCELLED,
    STATUS_PAID,
    STATUS_PENDING,
    TRANSITIONS,
)
from app.models import CartItem, IdempotencyRecord, Order, OrderItem, Product, utcnow
from app.payments import PaymentError, PaymentProvider
from app.schemas import OrderItemOut, OrderOut
from sn_shared.security import TokenPayload

SCOPE_CHECKOUT = "checkout"


def pay_scope(order_id: int) -> str:
    return f"pay:{order_id}"


def conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def order_view(order: Order, viewer_id: int) -> OrderOut:
    """The buyer sees every line; a seller sees only their own lines and subtotal."""
    lines = order.items if order.buyer_id == viewer_id else [
        item for item in order.items if item.seller_id == viewer_id
    ]
    items = [
        OrderItemOut(
            product_id=item.product_id,
            name=item.name,
            unit_price_cents=item.unit_price_cents,
            quantity=item.quantity,
            line_total_cents=item.unit_price_cents * item.quantity,
        )
        for item in lines
    ]
    return OrderOut(
        id=order.id,
        status=order.status,  # type: ignore[arg-type]
        currency=order.currency,
        total_cents=sum(item.line_total_cents for item in items),
        buyer_name=order.buyer_name,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items,
    )


def involved_order(db: Session, order_id: int, user_id: int) -> Order:
    """The order if the user is its buyer or a seller on it; otherwise 404 (no leak)."""
    order = db.get(Order, order_id)
    if order is None or not (
        order.buyer_id == user_id or any(item.seller_id == user_id for item in order.items)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _remembered_order(db: Session, user_id: int, scope: str, key: str | None) -> Order | None:
    if key is None:
        return None
    record = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    )
    return db.get(Order, record.order_id) if record else None


def _remember(db: Session, user_id: int, scope: str, key: str | None, order_id: int) -> None:
    if key is not None:
        db.add(IdempotencyRecord(user_id=user_id, scope=scope, key=key, order_id=order_id))


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


def checkout(db: Session, user: TokenPayload, key: str | None) -> tuple[Order, bool]:
    """Create an order from the cart. Returns (order, created); created is False on replay."""
    replay = _remembered_order(db, user.user_id, SCOPE_CHECKOUT, key)
    if replay is not None:
        return replay, False
    lines = _claim_cart(db, user.user_id)
    order = Order(
        buyer_id=user.user_id,
        buyer_name=user.username,
        status=STATUS_PENDING,
        currency=CURRENCY,
        total_cents=sum(product.price_cents * item.quantity for item, product in lines),
    )
    db.add(order)
    db.flush()
    for item, product in lines:
        _reserve_stock(db, item, product)
        order.items.append(
            OrderItem(
                product_id=product.id,
                seller_id=product.seller_id,
                name=product.name,
                unit_price_cents=product.price_cents,
                quantity=item.quantity,
            )
        )
    db.flush()
    _remember(db, user.user_id, SCOPE_CHECKOUT, key, order.id)
    try:
        db.commit()
    except IntegrityError:  # same key raced in from another request
        db.rollback()
        replay = _remembered_order(db, user.user_id, SCOPE_CHECKOUT, key)
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
    replay = _remembered_order(db, user.user_id, pay_scope(order_id), key)
    if replay is not None:
        return replay
    # Claim first (atomic status flip) so two concurrent pay calls cannot both charge.
    claimed = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == STATUS_PENDING)
        .values(status=STATUS_PAID, updated_at=utcnow())
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
        .values(payment_reference=result.reference)
        .execution_options(synchronize_session=False)
    )
    _remember(db, user.user_id, pay_scope(order_id), key, order_id)
    db.commit()
    db.refresh(order)
    return order


def _role_targets(order: Order, user_id: int) -> frozenset[str]:
    if order.buyer_id == user_id:
        return BUYER_TARGETS
    return SELLER_TARGETS  # involved_order already proved the user is a seller on it


def change_status(db: Session, user: TokenPayload, order_id: int, target: str) -> Order:
    order = involved_order(db, order_id, user.user_id)
    if target not in _role_targets(order, user.user_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may not set that status")
    if target not in TRANSITIONS[order.status]:
        raise conflict(f"Cannot move an order from {order.status} to {target}")
    current = order.status
    changed = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == current)  # guards against races
        .values(status=target, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise conflict("Order was changed by someone else, please reload")
    if target == STATUS_CANCELLED:
        for item in order.items:  # restock exactly what checkout took
            db.execute(
                update(Product)
                .where(Product.id == item.product_id)
                .values(stock=Product.stock + item.quantity)
                .execution_options(synchronize_session=False)
            )
    db.commit()
    db.refresh(order)
    return order
