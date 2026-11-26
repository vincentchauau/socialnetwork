"""The Werewolf game of a room (the video meeting is the `meeting` module)."""

from fastapi import Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload
from sqlalchemy.orm import sessionmaker

from api.chat import service, virtual_reply
from api.chat.routes_members import fill_with_virtual
from api.chat.routes_common import (
    Slug,
    member_in_open_room,
    new_router,
)
from api.chat.schemas import MessageOut
from api.chat import werewolf_remote

MIN_GAME_SEATS = 5
MAX_GAME_SEATS = 40

router = new_router()


def game_of(factory: sessionmaker, slug: str, user: TokenPayload) -> tuple[str, str, int, list[tuple[str, str]], bool]:
    """(the code of the room's game, the title of the room, the seats the game should have: one for each member, 5 to 40, and the
    names of the virtual people in the room: the seats nobody sits in take their names, played by the machine)."""
    with factory() as db:
        room = member_in_open_room(db, slug, user)
        made = True  # (said in the conversation once in a while: `announce_once` keeps count)
        code = service.game_code(room)
        seats = min(max(service.joined_members(db, room.id), MIN_GAME_SEATS), MAX_GAME_SEATS)
        title = room.title
        names = virtual_reply.member_names(db, room)
        db.commit()
        return code, title, seats, names, made


def fill_room(request: Request, slug: str, user: TokenPayload) -> None:
    """A game wants `MIN_GAME_SEATS` people: when the room has fewer, virtual people come in until it has them (the machine's players are virtual people)."""
    with request.app.state.session_factory() as db:
        room = member_in_open_room(db, slug, user)
        fill_with_virtual(request, db, room, slug, user, MIN_GAME_SEATS - service.joined_members(db, room.id))


def said_game(factory: sessionmaker, slug: str, user: TokenPayload) -> dict | None:
    """The line of the conversation that says who opened the game (once in a while), saved, as a frame to send."""
    with factory() as db:
        room = service.room_by_slug(db, slug)
        line = service.announce_once(db, room, "gameAnnounced", "game", user.user_id) if room else None
        db.commit()
        return MessageOut.model_validate(line).frame() if line else None


@router.post("/rooms/{slug}/game")
async def game(slug: Slug, request: Request, follow: bool = Query(False), user: TokenPayload = Depends(get_current_user)) -> dict:
    """The Werewolf game of the room, ready for this member: made the first time (with a seat for each member) and joined by
    the others, so they meet in one game. Returns its code. Opening it is said in the conversation, once in a while.
    `follow`: the people of the room changed and the game only follows them; virtual people come in to fill the seats only when it is asked for (not
    after somebody was sent away: the room is as its owner left it)."""
    factory = request.app.state.session_factory
    if not follow:
        await run_in_threadpool(fill_room, request, slug, user)
    code, title, seats, names, made = await run_in_threadpool(game_of, factory, slug, user)
    await run_in_threadpool(werewolf_remote.ensure_game, request.app, user.user_id, user.username, code, title, seats, names)
    frame = await run_in_threadpool(said_game, factory, slug, user) if made else None
    if frame:
        await request.app.state.hub.broadcast(slug, frame)
    return {"code": code, "seats": seats}
