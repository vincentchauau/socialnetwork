"""The tools the agent can use for a person, and the cards that show what they did.

A tool acts with the authority of the person who asked: the call to a service carries THAT person's token (given for this one
call, never kept or logged), so it can do exactly what the person could do in the page of that service, and no more. Tools that only
read run at once. Tools that change something run only when the same call says `confirmed`: without it they return a confirmation
card and touch nothing, and the card is shown to the person, whose click (not the model) confirms.

Cards are small JSON documents the chat shows in the room:
  {"type": "list", "title", "items": [{"title", "subtitle", "href", "actions": [...]}]}
  {"type": "detail", "title", "lines": [...], "image", "actions": [...]}
  {"type": "confirm", "tool", "args", "summary"}          (a question: nothing has happened)
  {"type": "form", "tool", "title", "fields": [...], "args", "submit"}   (a form to fill in: nothing has happened until it is sent)
  {"type": "done", "summary", "href"} / {"type": "error", "summary"}

An action is a button on a card: {"label", "tool", "args", "run"}. `run` says what the click does: "open" shows the result of the
tool (a list, a detail, a form: nothing changes), "do" does it at once (a small thing that can be undone), "ask" first shows a
confirmation card. The chat takes the tool and the arguments from the card it saved, never from the browser.
"""

import json
import os
import uuid
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

COOKIE_NAME = "sn_token"
TIMEOUT_SECONDS = 50  # the AI of art may take a while to answer
MAX_ITEMS = 5
TEXT_CHARS = 120
MAX_RESPONSE_BYTES = 256 * 1024


class ToolError(Exception):
    """The tool could not do it; the message is safe to show to the person."""


Http = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


def send_request(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed addresses of our own services
            return response.status, json.loads(response.read(MAX_RESPONSE_BYTES) or b"null")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read(MAX_RESPONSE_BYTES) or b"null")
        except ValueError:
            return error.code, None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        raise ToolError("That service is not answering right now") from None


def base(name: str) -> str:
    """Where a service answers: `<NAME>_URL`, else its module of this same backend (every module is mounted under its own name)."""
    try:
        return os.environ.get(f"{name.upper()}_URL", f"http://127.0.0.1:8000/{name}").rstrip("/")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("base failed")
        raise


def clip(value: Any, limit: int = TEXT_CHARS) -> str:
    try:
        text = " ".join(str(value or "").split())
        return text if len(text) <= limit else text[: limit - 1] + "…"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("clip failed")
        raise


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(min_length=1, max_length=64)


class Sell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    price_cents: int = Field(ge=1, le=1_000_000_000)


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddToCart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=99)


class Apply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int = Field(ge=1)


@dataclass(frozen=True)
class Tool:
    name: str
    args: type[BaseModel]
    writes: bool
    run: Callable[[BaseModel, str, Http], dict[str, Any]]
    summary: Callable[[BaseModel], str] = lambda args: ""
    # A tool with a form: asked without confirmation it returns the form (`form`, given the `opening` arguments such as which product);
    # the form sent back is the confirmation, and `args` then holds the opening arguments and the values together.
    form: Callable[[BaseModel, str, Http], dict[str, Any]] | None = None
    opening: type[BaseModel] = NoArgs


def field(name: str, label: str, kind: str, **more: Any) -> dict[str, Any]:
    """A field of a form card (see SchemaForm in the shared frontend)."""
    try:
        return {"name": name, "label": label, "kind": kind, **{k: v for k, v in more.items() if v is not None}}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("field failed")
        raise


def action(label: str, tool: str, args: dict[str, Any], run: str = "open") -> dict[str, Any]:
    try:
        return {"label": label, "tool": tool, "args": args, "run": run}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("action failed")
        raise


def form_card(tool: str, title: str, fields: list[dict[str, Any]], fixed: dict[str, Any], submit: str) -> dict[str, Any]:
    try:
        return {"type": "form", "tool": tool, "title": title, "fields": fields, "args": fixed, "submit": submit}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("form_card failed")
        raise


def site_path(value: Any) -> str | None:
    """An address of this site only (a card is never trusted to point elsewhere), else nothing."""
    try:
        return value if isinstance(value, str) and value.startswith("/") and not value.startswith("//") else None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("site_path failed")
        raise


def register(*tools: Tool) -> None:
    try:
        for tool in tools:
            TOOLS[tool.name] = tool
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("register failed")
        raise


def headers_tools(token: str) -> dict[str, str]:
    try:
        return {"Content-Type": "application/json", "Cookie": f"{COOKIE_NAME}={token}"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("headers_tools failed")
        raise


def get_tools(service: str, path: str, params: dict[str, Any], token: str, http: Http) -> Any:
    try:
        status, data = http("GET", f"{base(service)}{path}?{urllib.parse.urlencode(params)}", headers_tools(token), None)
        if status != 200 or data is None:
            raise ToolError("The search did not work")
        return data
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("get_tools failed")
        raise


def money(cents: int) -> str:
    try:
        return f"{cents / 100:,.2f}"
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("money failed")
        raise


def market_search(args: Query, token: str, http: Http) -> dict[str, Any]:
    try:
        page = get_tools("market", "/products", {"q": args.q, "limit": MAX_ITEMS}, token, http)
        items = [{"title": clip(p["name"]), "subtitle": f"{money(p['price_cents'])} · {clip(p['seller_username'], 32)}", "href": "/market"} for p in page["items"][:MAX_ITEMS]]
        return {"type": "list", "title": f"Market: {args.q}", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("market_search failed")
        raise


def jobs_search(args: Query, token: str, http: Http) -> dict[str, Any]:
    try:
        page = get_tools("job", "/jobs", {"q": args.q, "limit": MAX_ITEMS}, token, http)
        items = [
            {
                "title": f"#{p['id']} {clip(p['title'])}", "subtitle": f"{clip(p['company'], 40)} · {clip(p['location'], 40)}", "href": "/job",
                "actions": [action("Open", "jobs.job", {"job_id": p["id"]})],
            }
            for p in page["items"][:MAX_ITEMS]
        ]
        return {"type": "list", "title": f"Jobs: {args.q}", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("jobs_search failed")
        raise


def write(service: str, path: str, payload: dict[str, Any], token: str, http: Http, method: str = "POST", extra: dict[str, str] | None = None) -> Any:
    try:
        status, data = http(method, f"{base(service)}{path}", {**headers_tools(token), **(extra or {})}, json.dumps(payload).encode())
        if status in (200, 201, 204):
            return data
        detail = data.get("detail") if isinstance(data, dict) else None
        if isinstance(detail, list) and detail and isinstance(detail[0], dict):  # a field that does not fit: say which
            where = ".".join(str(part) for part in detail[0].get("loc", ())[1:])
            detail = f"{where}: {detail[0].get('msg', 'invalid')}" if where else str(detail[0].get("msg", "invalid"))
        raise ToolError(clip(detail) if isinstance(detail, str) else "It was refused")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("write failed")
        raise


def order_buttons(order: dict[str, Any], selling: bool) -> list[dict[str, Any]]:
    """What the buyer (or the seller) can still do with an order; the service decides again when it is pressed."""
    try:
        status = order["status"]
        if selling:
            return [action("Mark shipped", "market.orderstatus", {"order_id": order["id"], "status": "shipped"}, "ask")] if status == "paid" else []
        if status == "pending_payment":
            return [action("Pay", "market.pay", {"order_id": order["id"]}, "ask"), action("Cancel", "market.orderstatus", {"order_id": order["id"], "status": "cancelled"}, "ask")]
        if status == "paid":
            return [action("Cancel", "market.orderstatus", {"order_id": order["id"], "status": "cancelled"}, "ask")]
        if status == "shipped":
            return [action("I received it", "market.orderstatus", {"order_id": order["id"], "status": "delivered"}, "ask")]
        return []
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("order_buttons failed")
        raise


def market_cart(args: NoArgs, token: str, http: Http) -> dict[str, Any]:
    try:
        cart = get_tools("market", "/cart", {}, token, http)
        items = [
            {
                "title": f"{clip(line['name'])} x{line['quantity']}", "subtitle": money(line["line_total_cents"]), "href": "/market/cart",
                "actions": [action("Remove", "market.uncart", {"product_id": line["product_id"]}, "do")],
            }
            for line in cart["items"][:MAX_ITEMS]
        ]
        return {"type": "list", "title": f"Cart: {money(cart['total_cents'])} ({cart['item_count']})", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("market_cart failed")
        raise


def market_orders(args: NoArgs, token: str, http: Http) -> dict[str, Any]:
    try:
        page = get_tools("market", "/orders", {"limit": MAX_ITEMS}, token, http)
        items = [
            {"title": f"#{o['id']} {o['status']}", "subtitle": money(o["total_cents"]), "href": "/market/orders", "actions": order_buttons(o, selling=False)}
            for o in page["items"][:MAX_ITEMS]
        ]
        return {"type": "list", "title": "Orders", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("market_orders failed")
        raise


def market_add_to_cart(args: AddToCart, token: str, http: Http) -> dict[str, Any]:
    try:
        write("market", f"/cart/items/{args.product_id}", {"quantity": args.quantity}, token, http, method="PUT")
        return {"type": "done", "summary": f"Added {args.quantity} of product #{args.product_id} to your cart", "href": "/market/cart"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("market_add_to_cart failed")
        raise


def market_checkout(args: NoArgs, token: str, http: Http) -> dict[str, Any]:
    try:
        order = write("market", "/orders", {}, token, http, extra={"Idempotency-Key": uuid.uuid4().hex})
        return {"type": "done", "summary": f"Order #{order['id']} placed: {money(order['total_cents'])}", "href": "/market/orders"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("market_checkout failed")
        raise


def jobs_applications(args: NoArgs, token: str, http: Http) -> dict[str, Any]:
    try:
        rows = get_tools("job", "/me/applications", {}, token, http)
        items = [
            {
                "title": f"#{a['job_id']} {clip(a['job_title'])}", "subtitle": f"{clip(a['company'], 40)} · {a['status']}", "href": "/job/applications",
                "actions": [] if a["status"] == "hired" else [action("Withdraw", "jobs.withdraw", {"application_id": a["id"]}, "ask")],
            }
            for a in rows[:MAX_ITEMS]
        ]
        return {"type": "list", "title": "Your applications", "items": items}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("jobs_applications failed")
        raise


def market_sell(args: Sell, token: str, http: Http) -> dict[str, Any]:
    try:
        product = write("market", "/products", {"name": args.name, "price_cents": args.price_cents, "stock": 1}, token, http)
        return {"type": "done", "summary": f"Listed {clip(product['name'])} for {money(product['price_cents'])}", "href": "/market"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("market_sell failed")
        raise


def jobs_apply(args: Apply, token: str, http: Http) -> dict[str, Any]:
    try:
        write("job", f"/jobs/{args.job_id}/apply", {}, token, http)
        return {"type": "done", "summary": f"Applied to job #{args.job_id}", "href": "/job/applications"}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("jobs_apply failed")
        raise


TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool("market.search", Query, False, market_search),
        Tool("jobs.search", Query, False, jobs_search),
        Tool("market.cart", NoArgs, False, market_cart),
        Tool("market.orders", NoArgs, False, market_orders),
        Tool("jobs.applications", NoArgs, False, jobs_applications),
        Tool("market.addcart", AddToCart, True, market_add_to_cart, lambda a: f"Add {a.quantity} of product #{a.product_id} to your cart"),  # type: ignore[attr-defined]
        Tool("market.checkout", NoArgs, True, market_checkout, lambda a: "Place an order for everything in your cart"),
        Tool("market.sell", Sell, True, market_sell, lambda a: f"List {a.name} for sale at {money(a.price_cents)}"),  # type: ignore[attr-defined]
        Tool("jobs.apply", Apply, True, jobs_apply, lambda a: f"Apply to job #{a.job_id} with your profile"),  # type: ignore[attr-defined]
    )
}


def run_tool(name: str, args: dict[str, Any], token: str, confirmed: bool, http: Http = send_request) -> dict[str, Any]:
    """The card for this tool call. Raises KeyError for an unknown tool and ValueError for arguments that do not fit."""
    tool = TOOLS[name]
    if tool.form is not None and not confirmed:  # the form to fill in (nothing is written)
        try:
            opening = tool.opening.model_validate(args)
        except ValidationError:
            raise ValueError("Invalid arguments") from None
        if not token:
            return {"type": "error", "summary": "You need to be signed in"}
        try:
            return tool.form(opening, token, http)
        except ToolError as error:
            return {"type": "error", "summary": str(error)}
    try:
        parsed = tool.args.model_validate(args)
    except ValidationError as error:
        if tool.form is not None:  # a form that was sent: say which field does not fit, the form stays to be corrected
            first = error.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            return {"type": "error", "summary": clip(f"{where}: {first['msg']}")}
        raise ValueError("Invalid arguments") from None
    if tool.writes and not confirmed:
        return {"type": "confirm", "tool": name, "args": parsed.model_dump(), "summary": tool.summary(parsed)}
    if not token:
        return {"type": "error", "summary": "You need to be signed in"}
    try:
        return tool.run(parsed, token, http)
    except ToolError as error:
        return {"type": "error", "summary": str(error)}


# The tools of each service live in their own module and add themselves to TOOLS; they use the helpers above, so they come last.
from api.chat.agent import tools_face, tools_jobs, tools_market  # noqa: E402,F401

import logging
logger = logging.getLogger(__name__)
