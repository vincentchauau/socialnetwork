"""The messages of a room over HTTP: search and read the history, send, edit, delete, pin."""

import json
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sn_shared import textsearch
from api.chat import assistant, service
from api.chat.db import get_db
from api.chat.models import CARD_PREFIX, Message, Room
from api.chat.routes_common import (
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    Slug,
    emit,
    new_router,
    visible,
)
from api.chat.schemas import (
    MAX_MESSAGE_LENGTH,
    IncomingMessage,
    MessageOut,
)

router = new_router()


@router.get("/rooms/{slug}/messages", response_model=list[MessageOut])
def history(
    slug: Slug,
    limit: Annotated[int, Query(ge=1, le=HISTORY_MAX_LIMIT)] = HISTORY_DEFAULT_LIMIT,
    before: Annotated[int | None, Query(ge=1)] = None,
    q: Annotated[str, Query(max_length=80)] = "",
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Message]:
    """The history, newest last. With `q`, only the text messages that hold those words (any accent, any case), the same way."""
    room, me = visible(db, slug, user)
    if me is not None and me.status == service.BANNED_STATUS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.BANNED)
    query = select(Message).where(Message.room_id == room.id, Message.deleted_at.is_(None))
    if before is not None:
        query = query.where(Message.id < before)
    if q.strip():
        query = query.where(Message.kind == "text", textsearch.folded(Message.content).like(textsearch.pattern(q), escape="\\"))
    return service.show(db, reversed(db.scalars(query.order_by(Message.id.desc()).limit(limit)).all()))


def message_in(db: Session, room: Room, message_id: int) -> Message:
    message = db.get(Message, message_id)
    if message is None or message.room_id != room.id or message.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return message


@router.post("/rooms/{slug}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(slug: Slug, body: IncomingMessage, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    """Send a message without a socket: the same rules as the socket (a member, not muted, the room open, not waiting for an answer),
    saved and then sent to whoever has the room open."""
    room, me = visible(db, slug, user)
    problem = service.posting_problem(room, me)
    if problem is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, problem)
    if service.waiting_for_answer(db, room, user.user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, service.PENDING)
    reply_to = body.reply_to
    if reply_to is not None:
        target = db.get(Message, reply_to)
        if target is None or target.room_id != room.id or target.deleted_at is not None:
            reply_to = None  # the message answered is gone: this one stands on its own
    content = body.content.strip()
    if not content or content.startswith(CARD_PREFIX):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The message is empty")
    message = Message(room_id=room.id, user_id=user.user_id, content=content, reply_to_id=reply_to)
    db.add(message)
    db.commit()
    service.show_one(db, message)
    emit(request, slug, MessageOut.model_validate(message).frame())
    return message


class EditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


@router.patch("/rooms/{slug}/messages/{message_id}", response_model=MessageOut)
def edit_message(slug: Slug, message_id: int, body: EditBody, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> Message:
    """Only the author changes the words of a text message (the owner may delete it, not rewrite what someone said). It is marked edited."""
    room, me = visible(db, slug, user)
    message = message_in(db, room, message_id)
    if message.user_id != user.user_id or message.kind != "text":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot edit this message")
    problem = service.posting_problem(room, me)
    if problem is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, problem)
    content = body.content.strip()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The message is empty")
    message.content, message.edited_at = content, service.now()
    db.commit()
    emit(request, slug, {"type": "edited", "id": message_id, "content": message.content, "edited_at": message.edited_at.isoformat()})
    return service.show_one(db, message)


@router.delete("/rooms/{slug}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(slug: Slug, message_id: int, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """The author may delete their own message; the owner of the room may delete anyone's. It stays in the table, marked."""
    room, me = visible(db, slug, user)
    message = message_in(db, room, message_id)
    if message.user_id != user.user_id and not service.is_owner(room, me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot delete this message")
    message.deleted_at = service.now()
    message.pinned_at = None
    db.commit()
    emit(request, slug, {"type": "deleted", "id": message_id})


def _member_of(db: Session, slug: str, user: TokenPayload) -> Room:
    """The room, for anyone who is in it (a joined member): pinning is not for the moderators only."""
    room, me = visible(db, slug, user)
    if me is None or me.status != service.JOINED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
    return room


@router.put("/rooms/{slug}/messages/{message_id}/pin", status_code=status.HTTP_204_NO_CONTENT)
def pin_message(slug: Slug, message_id: int, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    room = _member_of(db, slug, user)
    message = message_in(db, room, message_id)
    message.pinned_at = service.now()
    db.commit()
    emit(request, slug, {"type": "pinned", "id": message_id, "pinned": True})


@router.delete("/rooms/{slug}/messages/{message_id}/pin", status_code=status.HTTP_204_NO_CONTENT)
def unpin_message(slug: Slug, message_id: int, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    room = _member_of(db, slug, user)
    message = message_in(db, room, message_id)
    message.pinned_at = None
    db.commit()
    emit(request, slug, {"type": "pinned", "id": message_id, "pinned": False})


CardAction = Annotated[str, Path(pattern="^(confirm|cancel)$")]
MAX_FORM_VALUES = 30
MAX_FORM_BYTES = 20_000


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any]


class ActBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: int | None = Field(default=None, ge=0, le=20)  # which row of a list the button is on
    action: int = Field(ge=0, le=10)


def _card_for(db: Session, slug: str, message_id: int, user: TokenPayload, kinds: tuple[str, ...] | None):
    """The room, the message and its card, when the person is a member of the open room and the card is for them."""
    room, me = visible(db, slug, user)
    if me is None or me.status != service.JOINED or room.state != service.OPEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
    message = message_in(db, room, message_id)
    card = assistant.decode(message)
    if card is None or (kinds is not None and card.get("type") not in kinds):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if card.get("for") != user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This card is for someone else")
    return room, message, card


def _post_card(request: Request, db: Session, room: Room, like: Message, card: dict) -> MessageOut:
    """Save a card as a message of the same virtual person and show it to the room."""
    saved = Message(room_id=room.id, user_id=like.user_id, content=assistant.encode(card))
    db.add(saved)
    db.commit()
    shown = MessageOut.model_validate(service.show_one(db, saved))
    emit(request, room.slug, shown.frame())
    return shown


def _set_card(db: Session, message: Message, before: str, card: dict) -> bool:
    """Replace the content of a card only if it still is `before`: of two clicks at once, one wins."""
    done = db.execute(update(Message).where(Message.id == message.id, Message.content == before).values(content=assistant.encode(card)))
    db.commit()
    return done.rowcount == 1


# (the routes with a word of their own come before the one with {action}: the first that matches the path is the one used)
@router.post("/rooms/{slug}/cards/{message_id}/submit", response_model=MessageOut)
def submit_card(slug: Slug, message_id: int, body: SubmitBody, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageOut:
    """The person a form is for sends it. It is the confirmation: the agent does it with THEIR token, once. If it does not fit, the form
    stays (with the reason) to be corrected; if it works, the form is closed and the result follows."""
    room, message, card = _card_for(db, slug, message_id, user, ("form",))
    if card.get("status") != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "This form was already sent")
    if len(body.values) > MAX_FORM_VALUES or len(json.dumps(body.values, default=str)) > MAX_FORM_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Too much in the form")
    before = message.content
    if not _set_card(db, message, before, {**card, "status": "running"}):  # taken: a second click finds it running
        raise HTTPException(status.HTTP_409_CONFLICT, "This form was already sent")
    args = {**body.values, **(card.get("args") or {})}  # what the form fixed (which product) cannot be changed by the values
    outcome = assistant.ask_tool(card["tool"], args, user.user_id, assistant.token_of(request.cookies), True) or assistant.failure()
    db.refresh(message)
    failed = outcome.get("type") == "error"
    closed = {**card, "status": "pending", "error": outcome.get("summary", "")} if failed else {**{k: v for k, v in card.items() if k != "error"}, "status": "done"}
    db.execute(update(Message).where(Message.id == message.id).values(content=assistant.encode(closed)))
    db.commit()
    db.refresh(message)
    shown = MessageOut.model_validate(service.show_one(db, message))
    emit(request, slug, shown.frame())
    if not failed:
        _post_card(request, db, room, message, assistant.for_person(outcome, user.user_id))
    return shown


@router.post("/rooms/{slug}/cards/{message_id}/act", response_model=MessageOut)
def act_on_card(slug: Slug, message_id: int, body: ActBody, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageOut:
    """A button of a card, pressed by the person the card is for. What it does comes from the card as saved: `open` shows the result,
    `do` does it at once, `ask` first puts a question in the room."""
    room, message, card = _card_for(db, slug, message_id, user, None)
    spec = assistant.action_of(card, body.item, body.action)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such button")
    token = assistant.token_of(request.cookies)
    run = spec.get("run")
    outcome = assistant.ask_tool(spec["tool"], spec["args"], user.user_id, token, run == "do") or assistant.failure()
    return _post_card(request, db, room, message, assistant.for_person(outcome, user.user_id))


@router.post("/rooms/{slug}/cards/{message_id}/{action}", response_model=MessageOut)
def answer_card(slug: Slug, message_id: int, action: CardAction, request: Request, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> MessageOut:
    """The person a card asks says yes or no. Only on `confirm` does the agent do the thing, with THEIR token, once."""
    room, me = visible(db, slug, user)
    if me is None or me.status != service.JOINED or room.state != service.OPEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, service.NOT_A_MEMBER)
    message = message_in(db, room, message_id)
    card = assistant.decode(message)
    if card is None or card.get("type") != "confirm":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if card.get("for") != user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This question is for someone else")
    if card.get("status") != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "This question was already answered")
    before = message.content
    if action == "cancel":
        if not _set_card(db, message, before, {**card, "status": "cancelled"}):
            raise HTTPException(status.HTTP_409_CONFLICT, "This question was already answered")
        outcome = None
    else:
        if not _set_card(db, message, before, {**card, "status": "running"}):  # taken: a second click finds it running
            raise HTTPException(status.HTTP_409_CONFLICT, "This question was already answered")
        outcome = assistant.ask_tool(card["tool"], card["args"], user.user_id, assistant.token_of(request.cookies), True) or assistant.failure()
        db.refresh(message)
        db.execute(update(Message).where(Message.id == message.id).values(content=assistant.encode({**card, "status": "failed" if outcome["type"] == "error" else "done"})))
        db.commit()
    db.refresh(message)
    shown = MessageOut.model_validate(service.show_one(db, message))
    emit(request, slug, shown.frame())
    if outcome is not None:
        result = Message(room_id=room.id, user_id=message.user_id, content=assistant.encode(outcome))
        db.add(result)
        db.commit()
        emit(request, slug, MessageOut.model_validate(service.show_one(db, result)).frame())
    return shown
