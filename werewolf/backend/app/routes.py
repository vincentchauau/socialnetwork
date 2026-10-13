from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine import (
    ABILITY_HELP,
    ALLOWED_ABILITIES,
    DEFAULT_ABILITIES,
    MAX_PLAYERS,
    MAX_TIMER,
    MIN_PLAYERS,
    MIN_TIMER,
    Ability,
    Faction,
    GameError,
    help_payload,
    suggest_roles,
    validate_roles,
)
from app.engine.chat import KEEP, MAX_LEN, MIN_INTERVAL
from app.history import list_history
from app.rooms import CapacityError, Forbidden, Room, RoomError, RoomNotFound
from app.schemas import (
    HISTORY_DEFAULT_LIMIT,
    HISTORY_MAX_LIMIT,
    ROOM_PATTERN,
    ActionBody,
    BotsBody,
    ChatBody,
    CreateBody,
    HistoryEntry,
    RoomSummary,
)
from app.security import check_origin
from app.service import commit, save_pending
from app.store import MAX_ROOMS_PER_USER
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter(dependencies=[Depends(check_origin)])
RoomCode = Annotated[str, Path(pattern=ROOM_PATTERN)]
TIMER_OPTIONS = [0, 30, 60, 90]


def http_error(error: Exception) -> HTTPException:
    """Room/engine errors to HTTP: 404 unknown room, 403 not allowed, 503 server full, 409 wrong state, 400 bad action."""
    if isinstance(error, RoomNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Room not found")
    if isinstance(error, Forbidden):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(error))
    if isinstance(error, CapacityError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    if isinstance(error, RoomError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(error))


async def current_user(request: Request, user: Annotated[TokenPayload, Depends(get_current_user)]) -> TokenPayload:
    """The authenticated user, within the per-user REST budget (429 beyond it).

    `async` on purpose: the store, the hub and the limiter are only ever touched from the event loop.
    """
    if not request.app.state.limits.allow("rest", user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down")
    return user


CurrentUser = Annotated[TokenPayload, Depends(current_user)]


def _limit(request: Request, kind: str, user: TokenPayload) -> None:
    if not request.app.state.limits.allow(kind, user.user_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down")


def _envelope(room: Room, user_id: int | None) -> dict[str, Any]:
    return {"id": room.code, "state": room.state_for(user_id)}


def _parse_roles(body: CreateBody) -> list[tuple[Faction, Ability]] | None:
    """The per-seat setup from the client, checked against the rules (422 on anything invalid)."""
    if body.seats is None:
        return None
    if body.count is not None and body.count != len(body.seats):
        raise HTTPException(422, "count does not match the number of seats")
    try:
        roles = [(Faction[s.faction], Ability[s.ability]) for s in body.seats]
        validate_roles(roles)
    except KeyError as error:
        raise HTTPException(422, f"Phe hoặc chức năng không hợp lệ: {error.args[0]}") from None
    except GameError as error:
        raise HTTPException(422, str(error)) from None
    return roles


async def _mutate(request: Request, code: str, user: TokenPayload, change) -> dict[str, Any]:
    """Apply `change(room)` (host/player checks live in Room), then store results and push the new state."""
    try:
        room = request.app.state.store.require(code)
        change(room)
    except GameError as error:
        raise http_error(error) from None
    except RoomNotFound as error:
        raise http_error(error) from None
    await commit(request.app, room)
    return _envelope(room, user.user_id)


# ---- setup (static, no auth needed) ----
@router.get("/setup/meta")
async def setup_meta() -> dict[str, Any]:
    """Factions, abilities (with rules text), defaults, help and limits so the client can build its pickers."""
    return {
        "minPlayers": MIN_PLAYERS,
        "maxPlayers": MAX_PLAYERS,
        "maxRoomsPerUser": MAX_ROOMS_PER_USER,
        "defaults": {f.name: labels for f, labels in DEFAULT_ABILITIES.items()},
        "factions": [{"code": f.name, "label": f.value} for f in Faction],
        "abilities": [{"code": a.name, "label": a.value, "help": ABILITY_HELP[a],
                       "allowedFactions": [f.name for f in Faction if a in ALLOWED_ABILITIES[f]]}
                      for a in Ability],
        "help": help_payload(),
        "timerOptions": TIMER_OPTIONS,
        "timerRange": [MIN_TIMER, MAX_TIMER],
        "chat": {"maxLength": MAX_LEN, "minIntervalSeconds": MIN_INTERVAL, "keep": KEEP},
    }


@router.get("/setup/random")
async def setup_random(count: Annotated[int, Query(ge=MIN_PLAYERS, le=MAX_PLAYERS)]) -> dict[str, Any]:
    """A balanced random faction/ability for each of `count` seats (seat 1 = the host); editable by the client."""
    return {"seats": [{"faction": f.name, "ability": a.name} for f, a in suggest_roles(count)]}


# ---- rooms ----
@router.post("/rooms", status_code=status.HTTP_201_CREATED)
async def create_room(request: Request, user: CurrentUser, body: CreateBody = CreateBody()) -> dict[str, Any]:
    _limit(request, "create", user)
    roles = _parse_roles(body)
    store = request.app.state.store
    try:
        room = store.create(
            user.user_id, user.username, roles=roles, count=body.count,
            title=(body.roomName or "").strip() or None, code=body.roomCode, timer=body.timerSeconds,
            events=body.events, dead_talk=body.deadTalk, listed=body.listed,
        )
        if body.start:
            try:
                room.start(user.user_id)
            except GameError:
                store.delete(room.code)
                raise
    except GameError as error:
        raise http_error(error) from None
    await commit(request.app, room)
    return _envelope(room, user.user_id)


@router.get("/rooms", response_model=list[RoomSummary])
async def list_rooms(request: Request, _user: CurrentUser) -> list[dict[str, Any]]:
    """Open lobbies (listed, not started, with a free bot seat), most recently active first."""
    return [room.summary() for room in request.app.state.store.open_lobbies()]


@router.get("/rooms/{code}")
async def get_room(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, Any]:
    room = request.app.state.store.get(code)
    if room is None:
        raise http_error(RoomNotFound(code))
    if room.seat_index(user.user_id) is None and room.started:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This game is already running")
    return _envelope(room, user.user_id)


@router.post("/rooms/{code}/join")
async def join_room(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, Any]:
    _limit(request, "join", user)
    store = request.app.state.store
    return await _mutate(request, code, user, lambda room: store.join(room.code, user.user_id, user.username))


@router.post("/rooms/{code}/leave")
async def leave_room(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, bool]:
    store = request.app.state.store
    try:
        room = store.leave(code, user.user_id)
    except (GameError, RoomNotFound) as error:
        raise http_error(error) from None
    if room is None:
        await request.app.state.hub.close_room(code.upper())
        await save_pending(request.app)  # the game the last human walked away from may have just finished
    else:
        await commit(request.app, room)
    return {"left": True}


@router.post("/rooms/{code}/start")
async def start_room(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _mutate(request, code, user, lambda room: room.start(user.user_id))


@router.post("/rooms/{code}/bots")
async def add_bots(code: RoomCode, body: BotsBody, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _mutate(request, code, user, lambda room: room.add_bots(user.user_id, body.count))


@router.post("/rooms/{code}/action")
async def action(code: RoomCode, body: ActionBody, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _mutate(request, code, user, lambda room: room.submit(user.user_id, body.target, body.kind))


@router.post("/rooms/{code}/chat")
async def chat(code: RoomCode, body: ChatBody, request: Request, user: CurrentUser) -> dict[str, Any]:
    _limit(request, "chat", user)
    try:
        room = request.app.state.store.require(code)
        message = room.chat(user.user_id, body.text, body.target)
    except (GameError, RoomNotFound) as error:
        raise http_error(error) from None
    await request.app.state.hub.send_chat(room.code, room.chat_recipients(message), room.chat_payload(message))
    return {"id": room.code, "message": room.chat_payload(message)}


@router.post("/rooms/{code}/force")
async def force(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _mutate(request, code, user, lambda room: room.force(user.user_id))


@router.post("/rooms/{code}/rematch")
async def rematch(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _mutate(request, code, user, lambda room: room.rematch(user.user_id))


@router.post("/rooms/{code}/reset")
async def reset(code: RoomCode, request: Request, user: CurrentUser) -> dict[str, Any]:
    return await _mutate(request, code, user, lambda room: room.reset(user.user_id))


@router.get("/rooms/{code}/perspective/{seat}")
async def perspective(code: RoomCode, seat: Annotated[int, Path(ge=1, le=MAX_PLAYERS)], request: Request,
                user: CurrentUser) -> dict[str, Any]:
    """What `seat` knows. Dead players, and everybody once the game is over; a living player gets 403."""
    try:
        return request.app.state.store.require(code).perspective(user.user_id, seat)
    except (GameError, RoomNotFound) as error:
        raise http_error(error) from None


@router.get("/me/history", response_model=list[HistoryEntry])
def my_history(
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=HISTORY_MAX_LIMIT)] = HISTORY_DEFAULT_LIMIT,
    db: Session = Depends(get_db),
) -> list[HistoryEntry]:
    return list_history(db, user.user_id, limit)
