from typing import Annotated, Any

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine import MAX_PLAYERS, ForbiddenAction, Game, GameError, Phase, leave, start_game, view_for
from app.history import list_history
from app.schemas import (
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    ROOM_PATTERN,
    HistoryEntry,
    RoomSummary,
)
from app.service import apply_sync
from app.store import RoomNotFound
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()
RoomId = Annotated[str, Path(pattern=ROOM_PATTERN)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


def _state(room_id: str, game: Game, user_id: int) -> dict[str, Any]:
    return {"id": room_id, "state": view_for(game, user_id)}


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, RoomNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")
    if isinstance(error, ForbiddenAction):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.post("/rooms", status_code=status.HTTP_201_CREATED)
def create_room(request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        room_id, game = request.app.state.store.create(user.user_id, user.username)
    except GameError as error:
        raise _http_error(error) from None
    return _state(room_id, game, user.user_id)


@router.get("/rooms", response_model=list[RoomSummary])
def list_rooms(request: Request, _user: CurrentUser) -> list[RoomSummary]:
    return [
        RoomSummary(
            id=room_id,
            host=game.find(game.host_id).username if game.find(game.host_id) else "",
            players=len(game.members()),
            max_players=MAX_PLAYERS,
        )
        for room_id, game in request.app.state.store.open_lobbies()
    ]


@router.get("/rooms/{room_id}")
def get_room(room_id: RoomId, request: Request, user: CurrentUser) -> dict[str, Any]:
    game = request.app.state.store.get(room_id)
    if game is None:
        raise _http_error(RoomNotFound(room_id))
    if game.member(user.user_id) is None and game.phase is not Phase.LOBBY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This game is already running")
    return _state(room_id, game, user.user_id)


@router.post("/rooms/{room_id}/join")
def join_room(room_id: RoomId, request: Request, user: CurrentUser) -> dict[str, Any]:
    try:
        game = request.app.state.store.join(room_id, user.user_id, user.username)
    except (GameError, RoomNotFound) as error:
        raise _http_error(error) from None
    from_thread.run(request.app.state.hub.broadcast_state, room_id, game)
    return _state(room_id, game, user.user_id)


@router.post("/rooms/{room_id}/leave")
def leave_room(room_id: RoomId, request: Request, user: CurrentUser) -> dict[str, bool]:
    try:
        apply_sync(request.app, room_id, lambda game: leave(game, user.user_id))
    except (GameError, RoomNotFound) as error:
        raise _http_error(error) from None
    return {"left": True}


@router.post("/rooms/{room_id}/start")
def start_room(room_id: RoomId, request: Request, user: CurrentUser) -> dict[str, Any]:
    rng = request.app.state.store.rng
    try:
        game = apply_sync(request.app, room_id, lambda g: start_game(g, user.user_id, rng))
    except (GameError, RoomNotFound) as error:
        raise _http_error(error) from None
    return _state(room_id, game, user.user_id)


@router.get("/me/history", response_model=list[HistoryEntry])
def my_history(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=HISTORY_MAX_LIMIT)] = HISTORY_DEFAULT_LIMIT,
    db: Session = Depends(get_db),
) -> list[HistoryEntry]:
    return list_history(db, user.user_id, limit)
