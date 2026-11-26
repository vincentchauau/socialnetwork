"""What the chat asks of the game, with a signed call (`sn_shared.servicesig`): the game of a room is made and joined, and goes with the room.

Nothing here is for a browser: the body is signed with `WEREWOLF_SECRET` (the same as the chat's), and an unsigned call is refused.
"""

import json
import os
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.werewolf.integration import ensure_game
from sn_shared import servicesig

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", include_in_schema=False)

MAX_BODY_BYTES = 16 * 1024


class EnsureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=16)
    title: str = Field(default="", max_length=200)
    seats: int = Field(ge=1, le=100)
    user_id: int
    username: str = Field(min_length=1, max_length=32)
    bot_names: list[tuple[str, str]] = Field(default_factory=list, max_length=100)


async def signed_internal(request: Request, scope: str) -> bytes:
    try:
        raw = await request.body()
        secret = os.environ.get("WEREWOLF_SECRET", "")
        if len(raw) > MAX_BODY_BYTES or not servicesig.verify(
            secret, raw, scope, request.headers.get(servicesig.TIMESTAMP_HEADER), request.headers.get(servicesig.SIGNATURE_HEADER)
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed")
        return raw
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("signed_internal failed")
        raise


@router.post("/ensure")
async def ensure(request: Request) -> dict[str, bool]:
    """The game under `code` exists and the person sits in it (see `ensure_game`)."""
    raw = await signed_internal(request, "POST /internal/ensure")
    try:
        body = EnsureBody.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid request") from None
    user = SimpleNamespace(user_id=body.user_id, username=body.username)
    await ensure_game(request.app, user, body.code, body.title, body.seats, [tuple(pair) for pair in body.bot_names])  # type: ignore[arg-type]
    return {"ok": True}


@router.delete("/rooms/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def drop(code: str, request: Request) -> Response:
    """The game of a room that is gone goes too (it would keep its players' seats, which count toward their limit)."""
    try:
        await signed_internal(request, f"DELETE /internal/rooms/{code}")
        request.app.state.ww_store.delete(code)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("drop failed")
        raise
