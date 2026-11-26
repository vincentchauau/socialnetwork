"""Admin CRUD (`/admin`) and the person's own twin (`/data`) for the market tables (see `sn_shared.admincrud`).

Deleting a product through the generic route would leave carts pointing at it and its reviews behind, so both mounts
run the same `on_delete`. Orders are payment records (status, total, payment references): they can be read and
deleted (admin) but not edited, so a row cannot be made to disagree with what the payment provider holds.

For a person (`/data`): their products (CRUD), their cart (CRUD), and the orders they bought or sold in (read only,
without the idempotency and payment keys).
"""

from fastapi import FastAPI, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.market.models import CartItem, Order, Product
from sn_shared import comments
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.security import TokenPayload


def delete_product(request: Request, db: Session, row, user: TokenPayload):
    product = db.get(Product, row["id"])
    if product is None:
        return None
    db.execute(delete(CartItem).where(CartItem.product_id == product.id))
    comments.forget_object(db, "product", product.id)
    db.delete(product)  # past orders keep their own snapshot (`Order.items`), which has no foreign key
    return None


def order_scope(db: Session, user: TokenPayload):
    """Orders I bought, and orders that have an item of mine (`seller_ids` is `|3|9|`)."""
    return (Order.buyer_id == user.user_id) | Order.seller_ids.contains(f"|{int(user.user_id)}|")


SPECS = [
    TableSpec(Product, owner="seller_id", on_delete=delete_product,
              media={"image_url": {"kind": "image", "preview": "@self"}}),
    TableSpec(CartItem, owner="user_id", refs={"product_id": ("market_products", "name")}),
    TableSpec(
        Order,  # an order is made by the checkout and shown to its buyer: nobody changes it through the records
        readonly_columns=("buyer_id", "total_cents", "items", "seller_ids", "created_at", "idempotency_key", "pay_key", "discount_cents", "delivered_at"),
        scope=order_scope,
        user_hidden_columns=("idempotency_key", "pay_key"),
    ),
]


def mount(app: FastAPI) -> None:
    mount_crud(app, SPECS, database="market")
