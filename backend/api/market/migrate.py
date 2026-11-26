"""Startup migration: order lines and idempotency keys moved into `orders`.

The old `order_items` and `idempotency_records` tables are only read, never changed or dropped (drop them by hand).
Only orders that have no items yet are filled, so it is safe to run at every start.
"""

from sqlalchemy import Text, bindparam, cast, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from api.market.models import Order, seller_ids_text
from sn_shared.db import ensure_columns

NEW_COLUMNS = {
    "items": "JSON NOT NULL DEFAULT '[]'",
    "seller_ids": "TEXT NOT NULL DEFAULT ''",
    "idempotency_key": "VARCHAR(128)",
    "pay_key": "VARCHAR(128)",
    "discount_cents": "BIGINT NOT NULL DEFAULT 0",
    "delivered_at": "TIMESTAMP WITH TIME ZONE",
}
PAY_PREFIX = "pay:"
CHECKOUT_SCOPE = "checkout"

LINES = text(
    "SELECT order_id, product_id, seller_id, name, unit_price_cents, quantity "
    "FROM order_items WHERE order_id IN :ids ORDER BY id"
).bindparams(bindparam("ids", expanding=True))
KEYS = text(
    "SELECT order_id, user_id, scope, key FROM idempotency_records WHERE order_id IN :ids ORDER BY id"
).bindparams(bindparam("ids", expanding=True))


def migrate_orders(engine: Engine) -> None:
    ensure_columns(engine, "market_orders", NEW_COLUMNS)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_buyer_idempotency ON market_orders (buyer_id, idempotency_key)")
        )
    tables = set(inspect(engine).get_table_names())
    with Session(engine) as db:
        empty = list(db.scalars(select(Order).where(cast(Order.items, Text) == "[]")))
        if not empty:
            return
        by_id = {order.id: order for order in empty}
        if "order_items" in tables:
            copy_lines(db, by_id)
        if "idempotency_records" in tables:
            copy_keys(db, by_id)
        db.commit()


def copy_lines(db: Session, orders: dict[int, Order]) -> None:
    lines: dict[int, list[dict]] = {}
    for row in db.execute(LINES, {"ids": list(orders)}):
        lines.setdefault(row.order_id, []).append(
            {
                "product_id": row.product_id,
                "seller_id": row.seller_id,
                "name": row.name,
                "unit_price_cents": row.unit_price_cents,
                "quantity": row.quantity,
            }
        )
    for order_id, items in lines.items():
        orders[order_id].items = items
        orders[order_id].seller_ids = seller_ids_text(items)


def copy_keys(db: Session, orders: dict[int, Order]) -> None:
    for row in db.execute(KEYS, {"ids": list(orders)}).all():
        order = orders[row.order_id]
        if row.user_id != order.buyer_id:
            continue
        if row.scope == CHECKOUT_SCOPE and order.idempotency_key is None:
            taken = db.scalar(
                select(Order.id).where(Order.buyer_id == order.buyer_id, Order.idempotency_key == row.key)
            )
            if taken is None:
                order.idempotency_key = row.key
                db.flush()
        elif row.scope == f"{PAY_PREFIX}{order.id}" and order.pay_key is None:
            order.pay_key = row.key
