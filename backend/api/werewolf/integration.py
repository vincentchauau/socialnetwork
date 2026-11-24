"""What the chat asks of the game: a room of the chat has a game of its own, made the first time and joined by the others."""

from fastapi import FastAPI, HTTPException, status
from sn_shared.security import TokenPayload

from api.werewolf.rooms import CapacityError, GameError, GameStarted, RoomFull, TooManyRooms
from api.werewolf.service import commit

TITLE_MAX = 30

# The reasons a person may not be seated, as the page knows them (it words them in the language of the person).
STARTED = "The game has started"
FULL = "The game is full"
TOO_MANY = "You are in too many games"
NO_ROOM = "No room left for a game"
TOO_FAST = "Too many requests, slow down"


async def ensure_game(app: FastAPI, user: TokenPayload, code: str, title: str, seats: int, bot_names: list[tuple[str, str]] | None = None) -> None:
    """The game under `code` exists (the first person makes it, with `seats` places) and `user` sits in it. Must run on the
    event loop: the rooms of the game are only touched from there."""
    store = app.state.ww_store
    room = store.get(code)
    if room is not None and room.follow_chat(bot_names or [], seats):
        await commit(app, room)  # the room has new virtual people (or more members) since the game was made: its seats follow
    if room is not None and room.seat_index(user.user_id) is not None:
        return
    if not app.state.ww_limits.allow("create" if room is None else "join", user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_FAST)
    try:
        if room is None:
            room = store.create(user.user_id, user.username, count=seats, title=title[:TITLE_MAX], code=code, listed=False, bot_names=bot_names)
        else:
            room = store.join(code, user.user_id, user.username)
    except TooManyRooms:
        raise HTTPException(status.HTTP_409_CONFLICT, TOO_MANY) from None
    except GameStarted:
        raise HTTPException(status.HTTP_409_CONFLICT, STARTED) from None
    except RoomFull:
        raise HTTPException(status.HTTP_409_CONFLICT, FULL) from None
    except CapacityError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_ROOM) from None
    except GameError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    await commit(app, room)
