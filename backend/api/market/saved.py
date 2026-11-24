"""The products a person keeps to look at again (like the jobs they save)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.market.db import get_db
from api.market.models import Product, SavedProduct
from api.market.products import ProductId, active_product_query, _outs
from api.market.schemas import ProductOut
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()
MAX_SAVED = 200


@router.put("/products/{product_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def save_product(
    product_id: ProductId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if db.execute(active_product_query().where(Product.id == product_id)).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    if db.scalar(select(SavedProduct.id).where(SavedProduct.user_id == user.user_id, SavedProduct.product_id == product_id)) is None:
        db.add(SavedProduct(user_id=user.user_id, product_id=product_id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/products/{product_id}/save", status_code=status.HTTP_204_NO_CONTENT)
def unsave_product(
    product_id: ProductId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.scalar(select(SavedProduct).where(SavedProduct.user_id == user.user_id, SavedProduct.product_id == product_id))
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/saved-products", response_model=list[ProductOut])
def my_saved_products(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ProductOut]:
    rows = db.execute(
        active_product_query()
        .join(SavedProduct, SavedProduct.product_id == Product.id)
        .where(SavedProduct.user_id == user.user_id)
        .order_by(SavedProduct.id.desc())
        .limit(MAX_SAVED)
    ).all()
    return _outs(db, list(rows))
