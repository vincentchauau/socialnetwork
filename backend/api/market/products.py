from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from sn_shared import directory
from sn_shared.columns import USERNAME_MAX
from sn_shared.comments import Comment

from api.market.constants import (
    CATEGORY_MAX,
    CURRENCY,
    MAX_PRICE_CENTS,
    PAGE_DEFAULT_LIMIT,
    PAGE_MAX_LIMIT,
    SEARCH_MAX,
)
from api.market.deps import expire_stale, get_db
from api.market.models import CartItem, Product
from api.market.schemas import ProductIn, ProductOut, ProductPage, RATING_DECIMALS
from sn_shared.deps import get_current_user
from sn_shared.facets import Facet, facets
from sn_shared.security import TokenPayload

import logging
logger = logging.getLogger(__name__)

router = APIRouter()

LIKE_ESCAPE = "\\"
ProductId = Annotated[int, Path(ge=1)]


def active_product_query() -> Select[Any]:
    """Active products with their review statistics (average, count)."""
    try:
        stats = (
            select(
                Comment.object_id.label("product_id"),
                func.avg(Comment.rating).label("average"),
                func.count(Comment.rating).label("count"),
            )
            .where(Comment.object_type == "product", Comment.rating.is_not(None))
            .group_by(Comment.object_id)
            .subquery()
        )
        return (
            select(Product, stats.c.average, stats.c.count)
            .outerjoin(stats, stats.c.product_id == Product.id)
            .where(Product.is_active.is_(True))
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("active_product_query failed")
        raise


def to_product_out(product: Product, average: float | None, count: int | None, seller_username: str) -> ProductOut:
    try:
        return ProductOut(
            id=product.id,
            seller_id=product.seller_id,
            seller_username=seller_username,
            name=product.name,
            description=product.description,
            price_cents=product.price_cents,
            currency=CURRENCY,
            stock=product.stock,
            image_url=product.image_url,
            category=product.category,
            rating_average=None if average is None else round(float(average), RATING_DECIMALS),
            review_count=count or 0,
            created_at=product.created_at,
        )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("to_product_out failed")
        raise


def load_product_out(db: Session, product_id: int) -> ProductOut:
    try:
        row = db.execute(active_product_query().where(Product.id == product_id)).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
        return outs(db, [row])[0]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("load_product_out failed")
        raise


def outs(db: Session, rows: list[Any]) -> list[ProductOut]:
    """Product views with the seller names read once for all rows."""
    try:
        found = directory.names(db, [row[0].seller_id for row in rows])
        return [to_product_out(row[0], row[1], row[2], found[row[0].seller_id]) for row in rows]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("outs failed")
        raise


def escape_like(term: str) -> str:
    try:
        return term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2).replace("%", "\\%").replace("_", "\\_")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("escape_like failed")
        raise


def page_products(db: Session, query: Select[Any], cursor: int | None, limit: int) -> ProductPage:
    try:
        if cursor is not None:
            query = query.where(Product.id < cursor)
        rows = db.execute(query.order_by(Product.id.desc()).limit(limit + 1)).all()
        page = rows[:limit]
        next_cursor = page[-1][0].id if len(rows) > limit else None
        return ProductPage(items=outs(db, page), next_cursor=next_cursor)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("page_products failed")
        raise


@router.get("/products", response_model=ProductPage, dependencies=[Depends(expire_stale)])
def list_products(
    q: Annotated[str | None, Query(max_length=SEARCH_MAX)] = None,
    category: Annotated[str | None, Query(max_length=CATEGORY_MAX)] = None,
    min_price: Annotated[int | None, Query(ge=0, le=MAX_PRICE_CENTS)] = None,
    max_price: Annotated[int | None, Query(ge=0, le=MAX_PRICE_CENTS)] = None,
    seller: Annotated[str | None, Query(max_length=USERNAME_MAX)] = None,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX_LIMIT)] = PAGE_DEFAULT_LIMIT,
    _user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductPage:
    try:
        if min_price is not None and max_price is not None and min_price > max_price:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "min_price exceeds max_price")
        query = active_product_query()
        if q and q.strip():
            pattern = f"%{escape_like(q.strip())}%"
            query = query.where(
                Product.name.ilike(pattern, escape=LIKE_ESCAPE)
                | Product.description.ilike(pattern, escape=LIKE_ESCAPE)
            )
        if category:
            query = query.where(Product.category == category.strip().lower())
        if min_price is not None:
            query = query.where(Product.price_cents >= min_price)
        if max_price is not None:
            query = query.where(Product.price_cents <= max_price)
        if seller:
            query = query.where(Product.seller_id.in_(select(directory.Person.user_id).where(func.lower(directory.Person.username) == seller.strip().lower())))
        return page_products(db, query, cursor, limit)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_products failed")
        raise


@router.get("/categories", response_model=list[Facet])
def list_categories(_user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Facet]:
    """The categories of the products on sale, the biggest first, with how many each holds."""
    try:
        return facets(db, Product.category, select(Product).where(Product.is_active.is_(True)))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("list_categories failed")
        raise


@router.get("/me/products", response_model=ProductPage, dependencies=[Depends(expire_stale)])
def my_products(
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX_LIMIT)] = PAGE_DEFAULT_LIMIT,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductPage:
    try:
        return page_products(db, active_product_query().where(Product.seller_id == user.user_id), cursor, limit)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("my_products failed")
        raise


@router.get(
    "/products/{product_id}", response_model=ProductOut, dependencies=[Depends(expire_stale)]
)
def get_product(
    product_id: ProductId,
    _user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductOut:
    try:
        return load_product_out(db, product_id)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_product failed")
        raise


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductOut:
    try:
        product = Product(seller_id=user.user_id, **body.model_dump())
        db.add(product)
        db.commit()
        return load_product_out(db, product.id)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_product failed")
        raise


def owned_product(db: Session, product_id: int, user: TokenPayload) -> Product:
    try:
        product = db.get(Product, product_id)
        if product is None or not product.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
        if product.seller_id != user.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this product")
        return product
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("owned_product failed")
        raise


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: ProductId,
    body: ProductIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProductOut:
    try:
        product = owned_product(db, product_id, user)
        for field, value in body.model_dump().items():
            setattr(product, field, value)
        db.commit()
        return load_product_out(db, product_id)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("update_product failed")
        raise


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: ProductId,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    # Soft delete: past orders keep their snapshot rows and foreign keys intact.
    try:
        product = owned_product(db, product_id, user)
        product.is_active = False
        db.execute(delete(CartItem).where(CartItem.product_id == product_id))
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("delete_product failed")
        raise
