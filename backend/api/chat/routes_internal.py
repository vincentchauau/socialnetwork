"""What the Werewolf tells the chat, with a signed call (`sn_shared.servicesig`): a game of one of its rooms is over.

Nothing here is for a browser: the body is signed with `WEREWOLF_SECRET` (the same on both sides) for exactly this call, and an
unsigned one is refused (the gateway does not let `/api/chat/internal/` through at all). The result is said in the room as a line of
`system` (`game_over:<winner>:<days>`) and a card with every role and what all of the players saw, once, to whoever has the room open.
Only what a finished game shows to everybody comes here: the game keeps what one player alone knew.
"""

import base64
import json
import os

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.chat import service, speech, voice_stream
from api.chat.schemas import MessageOut
from sn_shared import directory, servicesig

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)

MAX_BODY_BYTES = 32 * 1024
MAX_LINES = 120
MAX_LINE_CHARS = 200
CARD_BUDGET = 4500  # of the characters of a card (see `assistant.CARD_CHARS`): the end of the log goes first when it is longer
CARD_TITLE = "Ván Ma Sói đã kết thúc"
GAME_OVER_SCOPE = "POST /internal/game-over"
WINNERS = ("VILLAGER", "WOLF", "GHOST", "DRAW")


class GameOver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=16)
    winner: str = Field(min_length=1, max_length=16)
    days: int = Field(ge=0, le=1000)
    size: int = Field(ge=0, le=100)
    roles: list[str] = Field(default_factory=list, max_length=MAX_LINES)
    seen: list[str] = Field(default_factory=list, max_length=MAX_LINES)


def card_routes_internal(body: GameOver) -> dict:
    """The roles of everybody, then what happened that all of them saw, as the lines of a card that fits in a message."""
    try:
        lines: list[str] = []
        used = 0
        for heading, rows in (("Vai của mọi người", body.roles), ("Diễn biến", body.seen)):
            if not rows:
                continue
            lines.append(heading)
            used += len(heading)
            for row in rows:
                text = row.strip()[:MAX_LINE_CHARS]
                if used + len(text) > CARD_BUDGET:
                    break
                lines.append(text)
                used += len(text)
        return {"type": "detail", "title": CARD_TITLE, "lines": lines, "actions": []}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("card_routes_internal failed")
        raise


def say(request: Request, body: GameOver) -> tuple[str, list[dict]] | None:
    """The lines saved in the room whose game is `body.code`, with the frames to send; None when the chat has no such room."""
    try:
        with request.app.state.session_factory() as db:
            room = service.room_by_game_code(db, body.code)
            if room is None:
                return None
            winner = body.winner if body.winner in WINNERS else "DRAW"
            lines = [service.say_text(db, room, f"game_over:{winner}:{body.days}")]
            if body.roles or body.seen:
                lines.append(service.say_card(db, room, card_routes_internal(body)))
            db.commit()
            for line in lines:
                db.refresh(line)
            return room.slug, [MessageOut.model_validate(line).frame() for line in lines]
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("say failed")
        raise


@router.post("/game-over", status_code=status.HTTP_204_NO_CONTENT)
async def game_over(request: Request) -> Response:
    raw = await request.body()
    secret = os.environ.get("WEREWOLF_SECRET", "")
    if len(raw) > MAX_BODY_BYTES or not servicesig.verify(
        secret, raw, GAME_OVER_SCOPE, request.headers.get(servicesig.TIMESTAMP_HEADER), request.headers.get(servicesig.SIGNATURE_HEADER)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed")
    try:
        body = GameOver.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid request") from None
    said = await run_in_threadpool(say, request, body)
    if said is not None:
        slug, frames = said
        for frame in frames:
            await request.app.state.hub.broadcast(slug, frame)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


CALL_HEARD_SCOPE = "POST /internal/call-heard"
MAX_HEARD_BYTES = 2 * 1024 * 1024  # base64 of 30 seconds of PCM16 at 16 kHz is about 1.3 MB


@router.post("/call-heard", status_code=status.HTTP_204_NO_CONTENT)
async def call_heard(request: Request) -> Response:
    """What the ear of a call (the service that listens to the microphones in it) heard from one person: signed with `CALLEAR_SECRET`. It is made
    into words, written in the room as that person's message, and a virtual person answers when called by name or when the person is alone with them."""
    raw = await request.body()
    if len(raw) > MAX_HEARD_BYTES or not servicesig.verify(
        os.environ.get("CALLEAR_SECRET", ""), raw, CALL_HEARD_SCOPE, request.headers.get(servicesig.TIMESTAMP_HEADER), request.headers.get(servicesig.SIGNATURE_HEADER)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed")
    try:
        body = json.loads(raw)
        slug, identity, pcm, rate, humans = str(body["slug"])[:64], int(body["identity"]), str(body["pcm"]), int(body["rate"]), max(1, int(body.get("humans", 1)))
        sound = base64.b64decode(pcm, validate=True)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid request") from None
    if not 8000 <= rate <= 48000 or voice_stream.is_quiet(slug):
        return Response(status_code=status.HTTP_204_NO_CONTENT)  # (a virtual person is talking: this is its voice in the air)
    await run_in_threadpool(heard_in_call, request, slug, identity, sound, rate, humans)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def heard_in_call(request: Request, slug: str, user_id: int, sound: bytes, rate: int, humans: int) -> None:
    text = speech.transcribe(sound, rate)
    if len(text) < 2:
        return
    with request.app.state.session_factory() as db:
        username = directory.name_of(db, user_id)
    try:
        voice_stream.said_aloud(request, slug, user_id, username, text[:500], answer="named", humans=humans)
    except HTTPException:
        return  # (not a member of that room any more, or muted: nothing is written)
