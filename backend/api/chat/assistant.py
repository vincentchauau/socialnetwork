"""The assistant in a room: a line that starts with `/` asks the agent to use a tool for the person who wrote it.

    /market <words>   /jobs <words>      look for something (shown as a list card)
    /sell <name> <price>   /apply <job number>              change something: a card asks first, and only the click of the same
                                                            person on "Confirm" does it (the model never decides that)

The card is saved as a message of kind `card`, written by a virtual person of the room (so the room needs one). Its content is
JSON. A card that asks has `status` (`pending` -> `running` -> `done` | `failed` | `cancelled`) and `for` (the person who may answer it).
The token of the person is given to the agent for that one call only (the agent does not keep it).
"""

import json
import logging
import re
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sn_shared import COOKIE_NAME
from sqlalchemy.orm import sessionmaker

from api.chat import service, virtual_reply
from api.chat.agent import service as agent
from api.chat.models import CARD_PREFIX, Message
from api.chat.schemas import MessageOut

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60  # the agent may wait for a model
CARD_CHARS = 6000
SEARCHES: dict[str, str] = {}  # market and jobs are paused
SHOWS = {  # no words needed: a list, or a form to fill in
    "cart": "market.cart", "orders": "market.orders", "applications": "jobs.applications", "postjob": "jobs.post", "myjobs": "jobs.myjobs",
    "myproducts": "market.mine", "face": "face.measure", "measurements": "face.history", "clearmeasurements": "face.clear",
    "saved": "jobs.saved", "profile": "jobs.profile", "sales": "market.sales",
}
WITH_NUMBER = {  # one number: which job, product or course
    "applicants": ("jobs.applicants", "job_id"), "product": ("market.product", "product_id"),
    "editproduct": ("market.edit", "product_id"),
    "job": ("jobs.job", "job_id"), "editjob": ("jobs.editpost", "job_id"), 
    "reviews": ("market.reviews", "product_id"), "review": ("market.review", "product_id"), "pay": ("market.pay", "order_id"),
}
ASKS = {"checkout": "market.checkout"}
_SELL = re.compile(r"^(?P<name>.+?)\s+(?P<price>\d+(?:[.,]\d{1,2})?)$")
NO_ASSISTANT = "Bring a companion into the room to use commands"
USAGE = (
    "Usage: /market <words>, /jobs <words>, /product <number>, /cart, /orders, /applications, /addcart <product number> [how many], "
    "/checkout, /apply <job number>; for sellers /sell <name> <price>, /myproducts, /editproduct <number>; "
    "for employers /postjob, /myjobs, /applicants <job number>; "
    "/face to measure the symmetry of your face with the camera, /measurements to see the saved ones, /clearmeasurements; "
    "more: /job <n>, /saved, /profile, /editjob <n>, /sales, /pay <order>, /reviews <product>, /review <product>, "
    "for the owner of a room /owner, /mute, /unmute, /kick, /ban, /unban <name>, /close, /reopen"
)


def parse(content: str) -> tuple[str, dict[str, Any]] | None:
    """The tool and its arguments for a line like `/market lamp`, or None when the line is not a command (a plain message)."""
    if not content.startswith("/"):
        return None
    word, _, rest = content[1:].partition(" ")
    rest = rest.strip()
    command = word.lower()
    if command in SEARCHES:
        return (SEARCHES[command], {"q": rest[:64]}) if rest else ("", {})
    if command in SHOWS or command in ASKS:
        return ({**SHOWS, **ASKS}[command], {}) if not rest else ("", {})
    if command == "help":
        return "", {}  # the usage is the help
    if command in WITH_NUMBER:
        tool, key = WITH_NUMBER[command]
        return (tool, {key: int(rest)}) if rest.isdigit() and int(rest) > 0 else ("", {})
    if command == "addcart":
        first, _, count = rest.partition(" ")
        if first.isdigit() and int(first) > 0 and (not count or (count.strip().isdigit() and 0 < int(count) <= 99)):
            return "market.addcart", {"product_id": int(first), "quantity": int(count) if count else 1}
        return "", {}
    if command == "sell":
        match = _SELL.match(rest)
        if match is None:
            return "", {}
        cents = round(float(match["price"].replace(",", ".")) * 100)
        return "market.sell", {"name": match["name"].strip()[:80], "price_cents": cents}
    if command == "apply":
        return ("jobs.apply", {"job_id": int(rest)}) if rest.isdigit() and int(rest) > 0 else ("", {})
    return None


def ask_tool(tool: str, args: dict[str, Any], caller_id: int, token: str, confirmed: bool) -> dict[str, Any] | None:
    """The card from the agent, or None when it cannot run the tool (the room is then told it did not work)."""
    if not virtual_reply.agent_ready():
        return None
    card = agent.run_tool(tool, args, caller_id, token, confirmed)
    return card if isinstance(card, dict) and isinstance(card.get("type"), str) else None


def without_links(card: dict[str, Any]) -> dict[str, Any]:
    """The pages the old apps had are gone (everything is done in the chat), so a card does not point to them."""
    clean = {key: value for key, value in card.items() if key != "href"}
    if "items" in clean:
        clean["items"] = [{key: value for key, value in item.items() if key != "href"} for item in clean["items"] or []]
    return clean


def encode(card: dict[str, Any]) -> str:
    """The card as the text of a message, never longer than a message may be (list items are dropped from the end)."""
    card = without_links(card)
    items = list(card.get("items") or [])
    while True:
        text = json.dumps({**card, **({"items": items} if "items" in card else {})}, ensure_ascii=False, separators=(",", ":"))
        if len(text) <= CARD_CHARS or not items:
            return CARD_PREFIX + (text[:CARD_CHARS] if len(text) > CARD_CHARS else text)
        items.pop()


def decode(message: Message) -> dict[str, Any] | None:
    if message.kind != "card":
        return None
    try:
        card = json.loads(message.content[len(CARD_PREFIX):])
    except ValueError:
        return None
    return card if isinstance(card, dict) else None


def failure(summary: str = "The assistant could not do that right now") -> dict[str, Any]:
    return {"type": "error", "summary": summary}


def has_buttons(card: dict[str, Any]) -> bool:
    return bool(card.get("actions")) or any(item.get("actions") for item in card.get("items") or [])


def for_person(card: dict[str, Any], caller_id: int) -> dict[str, Any]:
    """A card that asks (a question, a form) gets its state and the one person who may answer it; so does a card with buttons."""
    if card.get("type") in ("confirm", "form", "camera"):
        return {**card, "status": "pending", "for": caller_id}
    return {**card, "for": caller_id} if has_buttons(card) else card


def action_of(card: dict[str, Any], item: int | None, index: int) -> dict[str, Any] | None:
    """The button at this place of the card as the chat saved it (the browser only says where it was clicked)."""
    try:
        actions = card["items"][item]["actions"] if item is not None else card["actions"]
        spec = actions[index]
    except (KeyError, IndexError, TypeError):
        return None
    return spec if isinstance(spec, dict) and isinstance(spec.get("tool"), str) and isinstance(spec.get("args"), dict) else None


def token_of(cookies: dict[str, str]) -> str:
    return cookies.get(COOKIE_NAME, "")


def save_card(factory: sessionmaker, slug: str, virtual_id: int, username: str, card: dict[str, Any]) -> MessageOut | None:
    """Save the card as a message of the virtual person, by the rules of the room; None when the room does not take it."""
    with factory() as db:
        room = service.room_by_slug(db, slug)
        if room is None or service.posting_problem(room, service.member_of(db, room.id, virtual_id)) is not None:
            return None
        message = Message(room_id=room.id, user_id=virtual_id, content=encode(card))
        db.add(message)
        db.commit()
        return MessageOut.model_validate(service.show_one(db, message))


def has_assistant(factory: sessionmaker, slug: str, author_id: int) -> bool:
    with factory() as db:
        return bool(virtual_reply.speakers(db, slug, author_id))


async def run_command(factory: sessionmaker, broadcast, slug: str, author, tool: str, args: dict[str, Any], token: str) -> None:
    """Called after the line of a person was saved and told to the room: the card comes back as a message of a virtual person."""
    try:
        def who() -> list[tuple[int, str]]:
            with factory() as db:
                return virtual_reply.speakers(db, slug, author.user_id)[:1]

        speaker = await run_in_threadpool(who)
        if not speaker:
            return
        card = await run_in_threadpool(ask_tool, tool, args, author.user_id, token, False) or failure()
        saved = await run_in_threadpool(save_card, factory, slug, speaker[0][0], speaker[0][1], for_person(card, author.user_id))
        if saved is not None:
            await broadcast(slug, saved.frame())
    except Exception:  # noqa: BLE001 - a failing command must never reach the person who wrote
        log.exception("a command failed")
