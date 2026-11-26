from sn_shared.db import ensure_foreign_key
from sn_shared.deps import access_dependencies
import asyncio
import json
import os
from types import SimpleNamespace
import re
import time
from collections import Counter
from collections.abc import Awaitable, AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sn_shared import directory, textsearch
from api.chat.social import models as social_models
from sn_shared.admincrud import TableSpec, mount_crud
from sn_shared.consumer import start_consumer, stop_consumer
from sn_shared.jwtkeys import require_verification_keys
from sn_shared.limits import SlidingWindow, UserRateLimiter
from sn_shared.security import AuthError, TokenPayload, payload_from_cookies
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import sessionmaker

from api.chat import assistant, room_commands, service, virtual_reply
from api.chat.db import Base, make_engine
from api.chat import cluster as clustering
from api.chat.lobby import LOBBY_KEY, Lobby
from api.chat.migrate import upgrade
from api.chat.models import Meeting, Message, Room, RoomMember
from sn_shared.origin import allowed_origins
from api.chat.presence import (
    MAX_LOBBY_SOCKETS_PER_USER,
    MAX_SOCKETS_PER_USER,
    Presence,
    presence_frame,
    system_frame,
)
from api.chat.rooms import RoomHub
from api.chat.routes_calls import router as calls_router
from api.chat.routes_meeting import router as meeting_router
from api.chat.routes_inbox import router as inbox_router
from api.chat.routes_members import router as members_router
from api.chat.routes_messages import router as messages_router
from api.chat.routes_internal import router as internal_router
from api.chat.routes_people import router as people_router
from api.chat.routes_rooms import router as rooms_router
from api.chat.schemas import ROOM_PATTERN, IncomingMessage, MessageOut

import logging
logger = logging.getLogger(__name__)

DEFAULT_DATABASE_URL = "sqlite:///./chat.db"
MAX_FRAME_CHARS = 8 * 1024
RATE_LIMIT_MESSAGES = 20
RATE_LIMIT_WINDOW_SECONDS = 10.0


def joined_room_ids(user: TokenPayload):
    try:
        return select(RoomMember.room_id).where(RoomMember.user_id == user.user_id, RoomMember.status == "joined")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("joined_room_ids failed")
        raise


def joined_rooms_scope(db, user: TokenPayload):
    try:
        return Room.id.in_(joined_room_ids(user))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("joined_rooms_scope failed")
        raise


def fellow_members_scope(db, user: TokenPayload):
    try:
        return RoomMember.room_id.in_(joined_room_ids(user))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("fellow_members_scope failed")
        raise


def joined_messages_scope(db, user: TokenPayload):
    try:
        return and_(Message.room_id.in_(joined_room_ids(user)), Message.deleted_at.is_(None))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("joined_messages_scope failed")
        raise


def enter(factory: sessionmaker, slug: str, user: TokenPayload) -> str | None:
    """Why this user may not open a socket in the room, or None: it must exist and they must be an active member."""
    try:
        with factory() as session:
            room = service.room_by_slug(session, slug)
            if room is None or room.state == service.DELETED:
                return service.NOT_FOUND
            member = service.member_of(session, room.id, user.user_id)
            if member is None or member.status in (service.LEFT, service.KICKED):
                return service.NOT_A_MEMBER
            if member.status == service.PENDING_STATUS:
                return service.PENDING
            if member.status == service.BANNED_STATUS:
                return service.BANNED
            return None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("enter failed")
        raise


def save_message(
    factory: sessionmaker, slug: str, user: TokenPayload, content: str, reply_to: int | None
) -> tuple[MessageOut | None, str | None]:
    """The saved message, or the reason it was not saved (a rule of the room: not a member, muted, closed...)."""
    try:
        with factory() as session:
            room = service.room_by_slug(session, slug)
            if room is None:
                return None, service.NOT_FOUND
            problem = service.posting_problem(room, service.member_of(session, room.id, user.user_id))
            if problem is not None:
                return None, problem
            if reply_to is not None:
                target = session.get(Message, reply_to)
                if target is None or target.room_id != room.id or target.deleted_at is not None:
                    reply_to = None  # the message answered is gone: this one stands on its own
            if service.waiting_for_answer(session, room, user.user_id):
                return None, service.PENDING  # a request is answered before it is followed by more
            message = Message(
                room_id=room.id, user_id=user.user_id, content=content, reply_to_id=reply_to
            )
            session.add(message)
            session.commit()
            return MessageOut.model_validate(service.show_one(session, message)), None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("save_message failed")
        raise


def parse_incoming(raw: str) -> IncomingMessage | None:
    """The validated message, or None when the frame is not a valid chat message."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        reply_to = data.get("reply_to")
        return IncomingMessage.model_validate(
            {
                "content": str(data.get("content", "")).strip(),
                "reply_to": reply_to if isinstance(reply_to, int) and not isinstance(reply_to, bool) else None,
            }
        )
    except (ValueError, ValidationError):
        return None


def valid_room(room: str) -> bool:
    try:
        return re.fullmatch(ROOM_PATTERN, room) is not None
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("valid_room failed")
        raise


stop_account_consumer = stop_consumer


TRY_AGAIN_LATER = 1013


class Expired(Exception):
    pass


def authorize(websocket: WebSocket) -> TokenPayload | None:
    """The user for a socket handshake, or None. Cookies are sent automatically by
    browsers, so a foreign page could open the socket on a visitor's behalf;
    browsers always send Origin, so a missing or foreign one is refused."""
    if websocket.headers.get("origin") not in allowed_origins():
        return None
    try:
        return payload_from_cookies(websocket.cookies)
    except AuthError:
        return None


async def receive_main(websocket: WebSocket, user: TokenPayload) -> str | None:
    """Next text frame; None for a binary one. The token is only checked at connect,
    so stop listening when it expires (raises Expired)."""
    remaining = max(user.expires_at - time.time(), 0)
    try:
        return await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
    except TimeoutError as error:
        raise Expired from error
    except KeyError:
        return None


def public_slugs_main(factory: sessionmaker) -> set[str]:
    try:
        with factory() as session:
            return service.public_slugs(session)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("public_slugs_main failed")
        raise


def delete_room(request, db, room, admin_user):
    """A room removed by an admin goes with its members and messages (nothing is left that points to it)."""
    try:
        room_id = room["id"]  # (the row is a mapping)
        db.execute(delete(Message).where(Message.room_id == room_id))
        db.execute(delete(RoomMember).where(RoomMember.room_id == room_id))
        db.execute(delete(Room).where(Room.id == room_id))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("delete_room failed")
        raise


def open_database(database_url: str | None) -> sessionmaker:
    """Make the engine, the tables, the old-data upgrade and the session factory of the chat."""
    try:
        engine = make_engine(database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        textsearch.register_sqlite(engine)
        Base.metadata.create_all(engine)
        for table in ("room_members", "messages", "meetings"):
            ensure_foreign_key(engine, table, "room_id", "rooms")
        social_models.ensure_tables(engine)  # the friendships, blocks and notices are the shared tables of `api.chat.social`
        directory.ensure_table_for_sqlite(engine)  # the people are read from `users` of center (a SQLite database has none: an empty one)
        session_factory = sessionmaker(engine, expire_on_commit=False)
        upgrade(engine, session_factory)  # an old database gets its rooms (made from the names its messages use)
        textsearch.ensure_postgres(engine)  # search without minding accents
        return session_factory
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("open_database failed")
        raise


def include_routers(app: FastAPI) -> None:
    try:
        app.include_router(rooms_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(members_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(messages_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(calls_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(meeting_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(inbox_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(people_router, dependencies=access_dependencies(admin=True, moderator=True, user=True))
        app.include_router(internal_router, dependencies=access_dependencies(public=True))
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("include_routers failed")
        raise


def mount_admin(app: FastAPI) -> None:
    # Admin CRUD over every table of the chat (admin role only). Deleting a room row does not remove its members and messages: hide a room
    # with `state: deleted` instead (see the room service) and use a hard delete only on an empty room.
    # /data (any signed-in person, reads only; writes stay in the app routes): the rooms the person has joined, their members and
    # live messages, and the person's own social edges, notices and reports.
    try:
        specs = [
            TableSpec(
                Room, on_delete=delete_room, scope=joined_rooms_scope),
            TableSpec(
                RoomMember, scope=fellow_members_scope,
                user_hidden_columns=("status_reason", "last_read_message_id", "hidden_at", "notify"),
                refs={"room_id": ("rooms", "title")}),
            TableSpec(
                Message, readonly_columns=("created_at",), scope=joined_messages_scope, refs={"room_id": ("rooms", "title")}),
            TableSpec(Meeting, owner="started_by", refs={"room_id": ("rooms", "title")}),
            TableSpec(social_models.Edge, owner="src_id"),
            TableSpec(social_models.Report, owner="reporter_id"),
            TableSpec(social_models.Notification, owner="user_id"),
        ]
        mount_crud(app, specs, database="chat")
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("mount_admin failed")
        raise


async def serve_lobby(websocket: WebSocket, rt: SimpleNamespace) -> None:
    hub, lobby, lobby_sockets, connections, online_users, people_changed = rt.hub, rt.lobby, rt.lobby_sockets, rt.connections, rt.online_users, rt.people_changed
    user = authorize(websocket)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    if lobby_sockets[user.user_id] >= MAX_LOBBY_SOCKETS_PER_USER:
        await websocket.close(code=TRY_AGAIN_LATER, reason="Too many lobby connections")
        return
    newly_online = user.user_id not in online_users()
    lobby_sockets[user.user_id] += 1
    if newly_online:
        await people_changed()  # before this socket is added: it gets its snapshot below, the others get the push
    lobby.hub.add(LOBBY_KEY, websocket)
    try:
        await websocket.send_json(lobby.frame())
        limiter = SlidingWindow(RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
        while True:
            try:
                raw = await receive_main(websocket, user)
            except Expired:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            if raw is not None and len(raw) > MAX_FRAME_CHARS:
                await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                return
            if not limiter.allow():
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            # The lobby is receive-only: client frames are counted and ignored.
    except WebSocketDisconnect:
        pass
    finally:
        lobby.hub.leave(LOBBY_KEY, websocket)
        lobby_sockets[user.user_id] -= 1
        if lobby_sockets[user.user_id] <= 0:
            del lobby_sockets[user.user_id]
            if user.user_id not in online_users():
                await asyncio.shield(people_changed())


async def answer_command(app: FastAPI, hub: RoomHub, room: str, user: TokenPayload, websocket: WebSocket, content: str) -> None:
    """A message that is not a command lets the virtual people of the room answer; a command is answered by the room's assistant."""
    try:
        command = assistant.parse(content)
        if command is None:
            virtual_reply.spawn(
                app.state.background, virtual_reply.reply_in_room(app.state.session_factory, hub.broadcast, room, user)
            )  # the writer does not wait for them
        elif not command[0]:
            await websocket.send_json({"type": "error", "error": assistant.USAGE})
        elif not await run_in_threadpool(assistant.has_assistant, app.state.session_factory, room, user.user_id):
            await websocket.send_json({"type": "error", "error": assistant.NO_ASSISTANT})
        else:  # a command: the assistant of the room answers with a card, in the name of a virtual person
            virtual_reply.spawn(
                app.state.background,
                assistant.run_command(app.state.session_factory, hub.broadcast, room, user, command[0], command[1], assistant.token_of(websocket.cookies)),
            )
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("answer_command failed")
        raise


async def serve_room(websocket: WebSocket, room: str, rt: SimpleNamespace) -> None:
    app, hub, presence, lobby, chat_sockets, connections, online_users, people_changed, presence_changed = rt.app, rt.hub, rt.presence, rt.lobby, rt.chat_sockets, rt.connections, rt.online_users, rt.people_changed, rt.presence_changed
    announce_leave = rt.announce_leave
    user = authorize(websocket)
    if user is None or not valid_room(room):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    not_allowed = await run_in_threadpool(enter, app.state.session_factory, room, user)
    if not_allowed is not None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=not_allowed)
        return
    refusal = None
    if chat_sockets[user.user_id] >= MAX_SOCKETS_PER_USER:
        refusal = "Too many connections"
    else:
        refusal = presence.refusal(room, user.user_id)
    if refusal is not None:
        await websocket.close(code=TRY_AGAIN_LATER, reason=refusal)
        return

    limiter = SlidingWindow(RATE_LIMIT_MESSAGES, RATE_LIMIT_WINDOW_SECONDS)
    newly_online = user.user_id not in online_users()
    chat_sockets[user.user_id] += 1
    if newly_online:
        await people_changed()
    first = presence.join(room, user.user_id, user.username)
    hub.add(room, websocket)
    connections.setdefault((room, user.user_id), set()).add(websocket)
    try:
        if first:
            await hub.broadcast(room, system_frame("join", room, user.user_id, user.username))
            await hub.broadcast_local(room, presence_frame(presence, room))
            await presence_changed(room)
            await lobby.notify()
        else:
            await websocket.send_json(presence_frame(presence, room))
        while True:
            try:
                raw = await receive_main(websocket, user)
            except Expired:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            if raw is None:  # binary frame
                await websocket.send_json({"type": "error", "error": "Only text frames are supported"})
                continue
            if len(raw) > MAX_FRAME_CHARS:
                await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                return
            if not limiter.allow():
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            incoming = parse_incoming(raw)
            if incoming is None:
                await websocket.send_json(
                    {"type": "error", "error": "Message must be 1-2000 characters"}
                )
                continue
            owned = room_commands.parse(incoming.content)
            if owned is None and (said := room_commands.parse_saying(incoming.content)) is not None:  # as people talk: the owner's only, else it is a message
                if await run_in_threadpool(room_commands.owns, app.state.session_factory, room, user.user_id):
                    owned = said
            if owned is not None:  # an owner's command (it is not a message, and a closed room takes it): the same as the buttons of the row
                problem = await room_commands.run(app, room, websocket.cookies, websocket.headers.get("origin", ""), owned[0], owned[1])
                if problem:
                    await websocket.send_json({"type": "error", "error": problem})
                continue
            saved, problem = await run_in_threadpool(
                save_message, app.state.session_factory, room, user, incoming.content, incoming.reply_to
            )
            if saved is None:
                await websocket.send_json({"type": "error", "error": problem})
                continue
            await hub.broadcast(room, saved.frame())
            await answer_command(app, hub, room, user, websocket, incoming.content)
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(room, websocket)
        sockets = connections.get((room, user.user_id))
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                del connections[(room, user.user_id)]
        chat_sockets[user.user_id] -= 1
        gone_offline = False
        if chat_sockets[user.user_id] <= 0:
            del chat_sockets[user.user_id]
            gone_offline = user.user_id not in online_users()
        if presence.leave(room, user.user_id):
            # Shielded: a cancelled handler must still tell the room the user left.
            await asyncio.shield(announce_leave(room, user))
        if gone_offline:
            await asyncio.shield(people_changed())


def wire_cluster(
    app: FastAPI,
    hub: RoomHub,
    presence: Presence,
    lobby: Lobby,
    session_factory: sessionmaker,
    remote_online: set[int],
    local_online: Callable[[], set[int]],
    close_sockets: Callable[[str, int, str], Awaitable[None]],
) -> tuple[Callable[[], Awaitable[None]], Callable[[str], Awaitable[None]], Callable[[], Awaitable[None]]]:
    """Connect this copy of the chat to the other copies (through Redis when it is set): what changes is sent, what they report is read."""
    try:
        async def cluster_changed() -> None:
            try:
                if app.state.cluster is not None:
                    await app.state.cluster.write_presence()
                    await app.state.cluster.publish({"t": "changed"})
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("cluster_changed failed")
                raise

        app.state.cluster_changed = cluster_changed

        async def people_changed() -> None:
            try:
                app.state.people_version += 1
                await lobby.notify()
                await cluster_changed()
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("people_changed failed")
                raise

        async def presence_changed(room: str) -> None:
            """Someone came to or left a room: the other copies learn it and show their sockets the whole room."""
            try:
                if app.state.cluster is not None:
                    await app.state.cluster.write_presence()
                    await app.state.cluster.publish({"t": "presence", "room": room})
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("presence_changed failed")
                raise

        async def refresh_remote() -> None:
            try:
                if app.state.cluster is None:
                    return
                rooms, online = await app.state.cluster.read_others()
                presence.set_remote(rooms)
                remote_online.clear()
                remote_online.update(online)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("refresh_remote failed")
                raise

        async def on_cluster_event(event: dict) -> None:
            try:
                kind = event.get("t")
                room = event.get("room")
                if kind == "frame" and isinstance(room, str) and isinstance(event.get("payload"), dict):
                    await hub.broadcast_local(room, event["payload"])
                elif kind == "close" and isinstance(room, str):
                    await close_sockets(room, int(event.get("user_id", 0)), str(event.get("reason", "")))
                elif kind == "presence" and isinstance(room, str):
                    await refresh_remote()
                    await hub.broadcast_local(room, presence_frame(presence, room))
                    await lobby.notify()
                elif kind == "changed":
                    await refresh_remote()
                    app.state.public_slugs = await run_in_threadpool(public_slugs_main, session_factory)
                    app.state.rooms_version += 1
                    app.state.people_version += 1
                    await lobby.notify()
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("on_cluster_event failed")
                raise

        async def start_cluster() -> None:
            try:
                client = getattr(app.state, "cluster_client", None)
                if client is None and clustering.enabled():
                    import redis.asyncio as aioredis

                    client = aioredis.from_url(os.environ["REDIS_URL"])
                if client is None:
                    return
                cluster = clustering.Cluster(client)
                app.state.cluster, hub.cluster = cluster, cluster
                await cluster.start(on_cluster_event, lambda: {"rooms": presence.local_rooms(), "online": sorted(local_online())}, refresh_remote)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("start_cluster failed")
                raise
        return people_changed, presence_changed, start_cluster
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("wire_cluster failed")
        raise


def create_app(database_url: str | None = None, clock: Callable[[], float] = time.monotonic) -> FastAPI:
    try:
        require_verification_keys()  # production without JWT_PUBLIC_KEYS fails at startup
        session_factory = open_database(database_url)

        @asynccontextmanager
        async def lifespan(application: FastAPI) -> AsyncIterator[None]:
            handle = start_consumer("chat", application.state.session_factory)
            await start_cluster()
            try:
                yield
            finally:
                await lobby.close()
                if application.state.cluster is not None:
                    await application.state.cluster.stop()
                if handle is not None:
                    await stop_account_consumer(handle)

        app = FastAPI(title="socialnetwork chat", lifespan=lifespan)
        app.state.session_factory = session_factory
        virtual_reply.bind(session_factory)
        app.state.background = set()  # tasks of the virtual replies, kept alive until done
        app.state.write_throttle = UserRateLimiter(max_events=60, window=10.0)  # one person may only write so often (reads are free)
        hub = RoomHub()
        presence = Presence()
        app.state.rooms_version = 0
        app.state.people_version = 0
        with session_factory() as session:
            app.state.public_slugs = service.public_slugs(session)
        chat_sockets: Counter[int] = Counter()  # open /ws sockets per user id, over all rooms
        lobby_sockets: Counter[int] = Counter()

        remote_online: set[int] = set()  # online in the other copies of the chat

        def local_online() -> set[int]:
            try:
                return set(chat_sockets) | set(lobby_sockets)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("local_online failed")
                raise

        def online_users() -> set[int]:
            """Who has the chat open: a socket in a room, or the lobby the page itself keeps (in any copy of the chat)."""
            try:
                return local_online() | remote_online
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("online_users failed")
                raise

        lobby = Lobby(
            presence,
            RoomHub(),
            allow=lambda slug: slug in app.state.public_slugs,
            extra=lambda: {"version": app.state.rooms_version, "people": app.state.people_version, "online": len(online_users())},
        )
        app.state.hub, app.state.presence, app.state.lobby, app.state.online_users = hub, presence, lobby, online_users

        app.state.cluster = None

        connections: dict[tuple[str, int], set[WebSocket]] = {}  # the sockets of one user in one room, to close on a ban

        async def disconnect(slug: str, user_id: int, reason: str) -> None:
            """Close the user's sockets in a room, in every copy of the chat (they were removed, banned, or the room is gone)."""
            try:
                await close_sockets(slug, user_id, reason)
                if app.state.cluster is not None:
                    await app.state.cluster.publish({"t": "close", "room": slug, "user_id": user_id, "reason": reason})
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("disconnect failed")
                raise

        async def close_sockets(slug: str, user_id: int, reason: str) -> None:
            try:
                for socket in list(connections.get((slug, user_id), ())):
                    try:
                        await socket.close(code=status.WS_1008_POLICY_VIOLATION, reason=reason[:120])
                    except Exception:  # already closed
                        pass
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("close_sockets failed")
                raise

        people_changed, presence_changed, start_cluster = wire_cluster(
            app, hub, presence, lobby, session_factory, remote_online, local_online, close_sockets
        )
        app.state.disconnect = disconnect
        include_routers(app)
        mount_admin(app)

        async def announce_leave(room: str, user: TokenPayload) -> None:
            try:
                await hub.broadcast(room, system_frame("leave", room, user.user_id, user.username))
                await hub.broadcast_local(room, presence_frame(presence, room))
                await presence_changed(room)
                await lobby.notify()
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("announce_leave failed")
                raise

        @app.get("/health", dependencies=access_dependencies(public=True))
        def health() -> dict[str, str]:
            try:
                return {"status": "ok"}
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("health failed")
                raise

        rt = SimpleNamespace(app=app, hub=hub, presence=presence, lobby=lobby, lobby_sockets=lobby_sockets,
                             chat_sockets=chat_sockets, connections=connections, online_users=online_users,
                             people_changed=people_changed, presence_changed=presence_changed, announce_leave=announce_leave)
        @app.websocket("/ws-lobby", dependencies=access_dependencies(admin=True, moderator=True, user=True))
        async def lobby_socket(websocket: WebSocket) -> None:
            try:
                await serve_lobby(websocket, rt)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("lobby_socket failed")
                raise

        @app.websocket("/ws/{room}", dependencies=access_dependencies(admin=True, moderator=True, user=True))
        async def chat_socket(websocket: WebSocket, room: str) -> None:
            try:
                await serve_room(websocket, room, rt)
            except Exception as error:
                if getattr(error, "status_code", None) is None:
                    logger.exception("chat_socket failed")
                raise

        return app
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("create_app failed")
        raise

