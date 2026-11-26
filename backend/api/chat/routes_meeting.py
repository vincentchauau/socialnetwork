"""The video call of a room: LiveKit holds the media, the chat decides who may be in it (the joined members of an open room) and gives them a ticket.

The virtual people are not in the video: they talk through the socket of the room (see `voice_stream`), whatever the call is."""

import base64
import secrets
import threading
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.chat import call_ear, livekit_tickets, service, speech, voice_stream
from api.chat.db import get_db
from api.chat.models import Meeting, Room, utcnow
from api.chat.routes_common import Slug, announce, visible
from sn_shared.clock import aware

router = APIRouter()

STALE_AFTER = timedelta(hours=3)  # an open meeting older than this is closed and a new one is made (a ticket lasts two hours)
MEETING_ANNOUNCED_KEY = "callAnnounced"  # ("a call was said a moment ago", kept in memory)
NOT_A_MEMBER = "You are not a member of this room"
ROOM_CLOSED = "This room is closed"
NOT_SET_UP = "Calls are not set up"


def out_routes_meeting(slug: str, meeting: Meeting, user: TokenPayload) -> dict[str, Any]:
    """What the browser needs to join: where LiveKit is, the name of its room, and the ticket of this person (members only get one)."""
    if not livekit_tickets.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP)
    return {
        "id": meeting.id, "room": slug, "name": meeting.room_name, "server": livekit_tickets.server_url(),
        "token": livekit_tickets.ticket(str(user.user_id), user.username, meeting.room_name),
    }


def open_meeting(db: Session, room_id: int) -> Meeting | None:
    """The room's open meeting; one older than `STALE_AFTER` is closed here and counts as none."""
    meeting = db.scalars(select(Meeting).where(Meeting.room_id == room_id, Meeting.ended_at.is_(None)).order_by(Meeting.id.desc()).limit(1)).first()
    if meeting is not None and utcnow() - aware(meeting.started_at) >= STALE_AFTER:
        meeting.ended_at = utcnow()
        return None
    return meeting


def end_all_open(db: Session, room_id: int) -> list[str]:
    """Close every open meeting of the room; returns their names at LiveKit (to be closed there too)."""
    names = []
    for meeting in db.scalars(select(Meeting).where(Meeting.room_id == room_id, Meeting.ended_at.is_(None))):
        meeting.ended_at = utcnow()
        names.append(meeting.room_name)
    return names


def close_at_livekit(names: list[str]) -> None:
    """Send the people out of those rooms (in the background: the answer of the route does not wait for LiveKit)."""
    for name in names:
        threading.Thread(target=livekit_tickets.close_room, args=(name,), daemon=True).start()


def member_room(db: Session, slug: str, user: TokenPayload, must_be_open: bool):
    room, me = visible(db, slug, user)
    if me is None or me.status != service.JOINED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_A_MEMBER)
    if must_be_open and room.state != service.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, ROOM_CLOSED)
    return room, me


@router.post("/rooms/{slug}/meeting/start")
def start_meeting(request: Request, slug: Slug, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """The meeting of the room, made if there is none open (one at a time), and the ticket to join it. That it started is said in the conversation,
    once in a while."""
    room, _me = member_room(db, slug, user, must_be_open=True)
    db.execute(select(Room.id).where(Room.id == room.id).with_for_update())  # two starts at once make one meeting, not two
    meeting = open_meeting(db, room.id)
    created = meeting is None
    if meeting is None:
        meeting = Meeting(room_id=room.id, room_name=f"sn-{secrets.token_urlsafe(12)}", started_by=user.user_id)
        db.add(meeting)
    line = service.announce_text_once(db, room, MEETING_ANNOUNCED_KEY, "meeting:both") if created else None
    db.commit()
    if line is not None:
        db.refresh(line)
        announce(request, slug, [line])
    out = out_routes_meeting(slug, meeting, user)
    call_ear.watch_in_background(meeting.room_name, slug)  # (the ear listens to the microphones of the call; asked at each join, it listens once)
    return out


@router.post("/rooms/{slug}/meeting/end", status_code=status.HTTP_204_NO_CONTENT)
def end_meeting(slug: Slug, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Ends the room's meeting: whoever started it, or the owner of the room."""
    room, me = member_room(db, slug, user, must_be_open=False)
    meeting = open_meeting(db, room.id)
    if meeting is None:
        db.commit()  # (a stale one was closed)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No meeting in this room")
    if meeting.started_by != user.user_id and not service.is_owner(room, me):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only who started the meeting or the owner of the room can end it")
    names = end_all_open(db, room.id)  # (all of them: an older one left open would be taken for the meeting of the room again)
    db.commit()
    close_at_livekit(names)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/rooms/{slug}/meeting")
def current_meeting(slug: Slug, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    room, _me = member_room(db, slug, user, must_be_open=False)
    meeting = open_meeting(db, room.id)
    db.commit()
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No meeting in this room")
    return out_routes_meeting(slug, meeting, user)


MAX_VOICE_SECONDS = 30
MIN_VOICE_RATE, MAX_VOICE_RATE = 8000, 48000


class VoiceMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pcm: str = Field(min_length=1, max_length=2_000_000)  # PCM16 mono, base64: 30 s at 16 kHz is about 1.3 MB
    rate: int = Field(ge=MIN_VOICE_RATE, le=MAX_VOICE_RATE)


@router.post("/rooms/{slug}/voice-message")
def send_a_voice_message(
    request: Request, slug: Slug, body: VoiceMessage, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The voice button of the room: the sound is made into words here, which are written in the room as the person's own message. The virtual
    people of the room answer it as they would a typed one, and read the answer aloud. The sound is not kept."""
    member_room(db, slug, user, must_be_open=False)
    try:
        pcm = base64.b64decode(body.pcm, validate=True)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The sound is not valid") from None
    if len(pcm) / 2 / body.rate > MAX_VOICE_SECONDS:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The message is too long")
    text = speech.transcribe(pcm, body.rate)
    if len(text) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nothing could be understood")
    return voice_stream.said_aloud(request, slug, user.user_id, user.username, text[:500], answer="always")
