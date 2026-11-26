"""Tools of the market: look at a product (a detail card), my products with edit and remove, and the edit form."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.chat.agent.tools import MAX_ITEMS, Http, NoArgs, Tool, get_tools, money, write, action, clip, field, form_card, register, site_path

import logging
logger = logging.getLogger(__name__)


class ProductId(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)


class EditProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    price: float | None = Field(default=None, gt=0, le=10_000_000)  # in the currency, not in cents
    stock: int | None = Field(default=None, ge=0, le=100_000)


def product(args: ProductId, token: str, http: Http) -> dict[str, Any]:
    try:
        p = get_tools("market", f"/products/{args.product_id}", {}, token, http)
        lines = [f"{money(p['price_cents'])} {p.get('currency', '')}".strip(), f"Seller: {clip(p['seller_username'], 32)}", f"In stock: {p['stock']}", f"Category: {clip(p['category'], 32)}"]
        if p.get("description"):
            lines.append(clip(p["description"], 300))
        card: dict[str, Any] = {
            "type": "detail",
            "title": clip(p["name"]),
            "lines": lines,
            "actions": [
                action("Add to cart", "market.addcart", {"product_id": p["id"], "quantity": 1}, "do"),
                action("Reviews", "market.reviews", {"product_id": p["id"]}),
                action("Write a review", "market.review", {"product_id": p["id"]}),
            ],
        }
        image = site_path(p.get("image_url"))
        if image:
            card["image"] = image
        return card
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("product failed")
        raise


def my_products(_: NoArgs, token: str, http: Http) -> dict[str, Any]:
    try:
        page = get_tools("market", "/me/products", {"limit": MAX_ITEMS}, token, http)
        items = [
            {
                "title": f"#{p['id']} {clip(p['name'])}",
                "subtitle": f"{money(p['price_cents'])} · {p['stock']} in stock",
                "href": "/market",
                "actions": [
                    action("Edit", "market.edit", {"product_id": p["id"]}),
                    action("Remove", "market.remove", {"product_id": p["id"]}, "ask"),
                ],
            }
            for p in page["items"][:MAX_ITEMS]
        ]
        return {"type": "list", "title": "Your products", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("my_products failed")
        raise


def edit_form(args: ProductId, token: str, http: Http) -> dict[str, Any]:
    try:
        p = get_tools("market", f"/products/{args.product_id}", {}, token, http)
        fields = [
            field("name", "Name", "text", required=True, max=80, value=p["name"]),
            field("description", "Description", "textarea", max=2000, value=p.get("description", "")),
            field("price", "Price", "number", required=True, min=0, step=0.01, value=p["price_cents"] / 100),
            field("stock", "In stock", "number", required=True, min=0, value=p["stock"]),
        ]
        return form_card("market.edit", f"Edit {clip(p['name'], 40)}", fields, {"product_id": args.product_id}, "Save")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("edit_form failed")
        raise


def edit_product(args: EditProduct, token: str, http: Http) -> dict[str, Any]:
    try:
        current = get_tools("market", f"/products/{args.product_id}", {}, token, http)
        body = {
            "name": args.name if args.name is not None else current["name"],
            "description": args.description if args.description is not None else current.get("description", ""),
            "price_cents": round(args.price * 100) if args.price is not None else current["price_cents"],
            "stock": args.stock if args.stock is not None else current["stock"],
            "category": current["category"],
            "image_url": current.get("image_url"),
        }
        write("market", f"/products/{args.product_id}", body, token, http, method="PUT")
        return {"type": "done", "summary": f"Saved {clip(body['name'], 40)}", "href": "/market"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("edit_product failed")
        raise


def remove_product(args: ProductId, token: str, http: Http) -> dict[str, Any]:
    try:
        write("market", f"/products/{args.product_id}", {}, token, http, method="DELETE")
        return {"type": "done", "summary": f"Removed product #{args.product_id}", "href": "/market"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("remove_product failed")
        raise


register(
    Tool("market.product", ProductId, False, product),
    Tool("market.mine", NoArgs, False, my_products),
    Tool("market.edit", EditProduct, True, edit_product, lambda a: f"Save the changes to product #{a.product_id}", form=edit_form, opening=ProductId),  # type: ignore[attr-defined]
    Tool("market.remove", ProductId, True, remove_product, lambda a: f"Remove product #{a.product_id} from sale"),  # type: ignore[attr-defined]
)


# ---- market: take things out of the cart, pay, follow orders (as a buyer and as a seller), reviews ---------------------------------


class OrderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(ge=1)


class OrderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(ge=1)
    status: str = Field(pattern="^(shipped|delivered|cancelled)$")


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    rating: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=1000)


def uncart(args: ProductId, token: str, http: Http) -> dict[str, Any]:
    try:
        write("market", f"/cart/items/{args.product_id}", {}, token, http, method="DELETE")
        return {"type": "done", "summary": f"Took product #{args.product_id} out of your cart", "href": "/market/cart"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("uncart failed")
        raise


def sales(_: NoArgs, token: str, http: Http) -> dict[str, Any]:
    try:
        from api.chat.agent.tools import order_buttons

        page = get_tools("market", "/sales", {"limit": MAX_ITEMS}, token, http)
        items = [
            {"title": f"#{o['id']} {o['status']} · {clip(o['buyer_username'], 24)}", "subtitle": money(o["total_cents"]), "href": "/market/orders", "actions": order_buttons(o, selling=True)}
            for o in page["items"][:MAX_ITEMS]
        ]
        return {"type": "list", "title": "Orders you sell", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("sales failed")
        raise


def pay(args: OrderRef, token: str, http: Http) -> dict[str, Any]:
    try:
        order = write("market", f"/orders/{args.order_id}/pay", {}, token, http, extra={"Idempotency-Key": uuid.uuid4().hex})
        return {"type": "done", "summary": f"Order #{args.order_id} is {order['status']}", "href": "/market/orders"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("pay failed")
        raise


def order_status(args: OrderStatus, token: str, http: Http) -> dict[str, Any]:
    try:
        order = write("market", f"/orders/{args.order_id}/status", {"status": args.status}, token, http, method="PATCH")
        return {"type": "done", "summary": f"Order #{args.order_id} is now {order['status']}", "href": "/market/orders"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("order_status failed")
        raise


def reviews(args: ProductId, token: str, http: Http) -> dict[str, Any]:
    try:
        rows = get_tools("market", f"/products/{args.product_id}/reviews", {"limit": MAX_ITEMS}, token, http)
        items = [{"title": f"{'★' * r['rating']}{'☆' * (5 - r['rating'])} {clip(r['username'], 24)}", "subtitle": clip(r["content"] or "", 120)} for r in rows[:MAX_ITEMS]]
        return {"type": "list", "title": f"Reviews of product #{args.product_id}", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("reviews failed")
        raise


def review_form(args: ProductId, token: str, http: Http) -> dict[str, Any]:
    try:
        fields = [
            field("rating", "Stars (1 to 5)", "select", required=True, value="5", options=[{"value": str(n), "label": "★" * n} for n in (5, 4, 3, 2, 1)]),
            field("content", "Your review", "textarea", max=1000),
        ]
        return form_card("market.review", f"Review product #{args.product_id}", fields, {"product_id": args.product_id}, "Post the review")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("review_form failed")
        raise


def post_review(args: Review, token: str, http: Http) -> dict[str, Any]:
    try:
        write("market", f"/products/{args.product_id}/reviews", {"rating": args.rating, "content": args.content}, token, http)
        return {"type": "done", "summary": f"Thanks for reviewing product #{args.product_id}"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("post_review failed")
        raise


register(
    Tool("market.uncart", ProductId, True, uncart, lambda a: f"Take product #{a.product_id} out of your cart"),  # type: ignore[attr-defined]
    Tool("market.sales", NoArgs, False, sales),
    Tool("market.pay", OrderRef, True, pay, lambda a: f"Pay order #{a.order_id}"),  # type: ignore[attr-defined]
    Tool("market.orderstatus", OrderStatus, True, order_status, lambda a: f"Mark order #{a.order_id} as {a.status}"),  # type: ignore[attr-defined]
    Tool("market.reviews", ProductId, False, reviews),
    Tool("market.review", Review, True, post_review, lambda a: f"Post a {a.rating}-star review", form=review_form, opening=ProductId),  # type: ignore[attr-defined]
)
