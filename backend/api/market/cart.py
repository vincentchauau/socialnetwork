from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.market.constants import CURRENCY, MAX_CART_PRODUCTS
from api.market.deps import expire_stale, get_db
from api.market.models import CartItem, Product
from api.market.schemas import CartItemIn, CartLineOut, CartOut
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

ProductId = Annotated[int, Path(ge=1)]


def build_cart(db: Session, user_id: int) -> CartOut:
    """The cart priced from current database prices (never from the client)."""
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, Product.id == CartItem.product_id)
        .where(CartItem.user_id == user_id, Product.is_active.is_(True))
        .order_by(CartItem.id)
    ).all()
    lines = [
        CartLineOut(
            product_id=product.id,
            name=product.name,
            image_url=product.image_url,
            unit_price_cents=product.price_cents,
            quantity=item.quantity,
            line_total_cents=product.price_cents * item.quantity,
            stock=product.stock,
        )
        for item, product in rows
    ]
    return CartOut(
        items=lines,
        currency=CURRENCY,
        item_count=sum(line.quantity for line in lines),
        total_cents=sum(line.line_total_cents for line in lines),
    )


def _set_quantity(db: Session, user_id: int, product_id: int, quantity: int) -> None:
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
    )
    if item is None:
        distinct = db.scalar(select(func.count(CartItem.id)).where(CartItem.user_id == user_id))
        if (distinct or 0) >= MAX_CART_PRODUCTS:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A cart can hold at most {MAX_CART_PRODUCTS} products"
            )
        db.add(CartItem(user_id=user_id, product_id=product_id, quantity=quantity))
    else:
        item.quantity = quantity
    db.commit()


@router.get("/cart", response_model=CartOut)
def get_cart(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> CartOut:
    return build_cart(db, user.user_id)


@router.put(
    "/cart/items/{product_id}", response_model=CartOut, dependencies=[Depends(expire_stale)]
)
def put_cart_item(
    product_id: ProductId,
    body: CartItemIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartOut:
    if body.quantity == 0:
        return remove_cart_item(product_id, user, db)
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    if product.seller_id == user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot buy your own product")
    if body.quantity > product.stock:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only {product.stock} in stock")
    try:
        _set_quantity(db, user.user_id, product_id, body.quantity)
    except IntegrityError:  # a concurrent request inserted the same line first
        db.rollback()
        _set_quantity(db, user.user_id, product_id, body.quantity)
    return build_cart(db, user.user_id)


@router.delete("/cart/items/{product_id}", response_model=CartOut)
def remove_cart_item(
    product_id: ProductId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartOut:
    db.execute(
        delete(CartItem).where(CartItem.user_id == user.user_id, CartItem.product_id == product_id)
    )
    db.commit()
    return build_cart(db, user.user_id)


@router.delete("/cart", response_model=CartOut)
def clear_cart(
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CartOut:
    db.execute(delete(CartItem).where(CartItem.user_id == user.user_id))
    db.commit()
    return build_cart(db, user.user_id)
