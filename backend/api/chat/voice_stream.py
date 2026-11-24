"""Talking with the virtual people of a room, aloud.

A person says something (the voice button of the room, or the microphone in a call: the sound is made into words here); the room writes it as
theirs; one virtual person of the room answers, in the room too; and the answer is read aloud SENTENCE BY SENTENCE: each sentence is made into a voice and sent at once to everybody who has the room open
(a frame `voice`), so the first sound comes before the last sentence is made. A request to "share the screen" makes a slide of words (a frame
`slide`) that everybody sees. Nothing here uses the video of the calls: the virtual people are not in it.

Frames (the socket of the room): `{"type": "voice", "id", "seq", "last", "user_id", "username", "name", "text", "pcm", "rate"}` and
`{"type": "slide", "user_id", "name", "title", "lines"}` (no lines: the slide is taken away).
"""

import base64
import re
import secrets
import time

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.chat import service, speech, virtual_reply
from sn_shared.directory import Person
from api.chat.models import Message, RoomMember
from api.chat.routes_common import emit
from api.chat.schemas import MessageOut

MAX_IN_CALL = 3
SLIDE_LINES = 5
SENTENCE = re.compile(r"(?<=[.!?…。])\s+|\n+")
SHARE_ASK = re.compile(r"(chia sẻ|trình chiếu|share|present).*(màn hình|screen|slide)|(màn hình|screen).*(chia sẻ|share)", re.IGNORECASE)
STOP_SHARE = re.compile(r"(dừng|ngừng|tắt|stop|end).*(chia sẻ|share|trình chiếu)", re.IGNORECASE)
SLIDE_PROMPT = "In the language of the topic, write {n} short bullet points (at most 8 words each), one per line, no numbering and no extra words, for a slide about: {topic}"


def virtual_members(db: Session, slug: str) -> list[tuple[int, str, str, str]]:
    """The virtual people who are joined in the open room: (user id, username, name, picture), at most `MAX_IN_CALL`."""
    room = service.room_by_slug(db, slug)
    if room is None or room.state != service.OPEN:
        return []
    rows = db.execute(
        select(Person).join(RoomMember, RoomMember.user_id == Person.user_id)
        .where(RoomMember.room_id == room.id, RoomMember.status == service.JOINED, Person.kind == "virtual").order_by(Person.user_id).limit(MAX_IN_CALL)
    ).scalars().all()
    out = []
    for person in rows:
        seen = person.view()
        out.append((person.user_id, person.username, seen.display_name or person.username, seen.avatar or ""))
    return out


_LAST_SPEAKER: dict[str, int] = {}


def who_answers(speakers: list[tuple[int, str, str, str]], text: str, slug: str | None = None) -> tuple[int, str, str, str]:
    """The one called by name; else the one after the one who spoke last in this room (so they take turns), the first when nobody has."""
    called = text.lower().replace("_", " ")
    named = next((s for s in speakers if s[1].lower().replace("_", " ") in called or s[2].lower() in called), None)
    if named is not None:
        chosen = named
    else:
        last = _LAST_SPEAKER.get(slug or "")
        ids = [s[0] for s in speakers]
        chosen = speakers[(ids.index(last) + 1) % len(speakers)] if last in ids else speakers[0]
    if slug:
        _LAST_SPEAKER[slug] = chosen[0]
    return chosen


def sentences(text: str) -> list[str]:
    """The text in pieces to read one after the other (a long piece is not made into one voice: the first sound would wait for all of it)."""
    return [piece.strip() for piece in SENTENCE.split(text) if piece.strip()]


def slide_of(topic: str, speaker_id: int, caller_id: int) -> list[str]:
    """Words for a slide about the topic, from the same model that gives the virtual person its words."""
    text = virtual_reply.ask_agent(speaker_id, caller_id, "everyone in the call", [{"username": "meeting", "content": SLIDE_PROMPT.format(n=SLIDE_LINES, topic=topic[:200])}])
    lines = [re.sub(r"^[\s•*\-–\d.)]+", "", line).strip() for line in (text or "").splitlines()]
    return [line for line in lines if line][:SLIDE_LINES]


def voice_frames(speaker: tuple[int, str, str, str], reply: str):
    """The frames that read the answer aloud, one per sentence, each made when it is asked for (a generator: the caller sends each as it comes)."""
    uid, username, name, _avatar = speaker
    pieces = sentences(reply) or [reply]
    utterance = secrets.token_hex(6)
    for number, piece in enumerate(pieces):
        made = speech.synthesize(piece, speech.voice_of(username))
        yield {
            "type": "voice", "id": utterance, "seq": number, "last": number == len(pieces) - 1, "user_id": uid, "username": username, "name": name, "text": piece,
            "pcm": base64.b64encode(made[0]).decode() if made else None, "rate": made[1] if made else None,
        }


ECHO_SECONDS = 1.5  # after a virtual person has finished, what the microphones hear is still their voice in the air
_QUIET_UNTIL: dict[str, float] = {}


def mark_speaking(slug: str, seconds: float) -> None:
    """A virtual person is reading aloud in this room for this long: what the microphones of the call hear meanwhile is not a person."""
    _QUIET_UNTIL[slug] = max(_QUIET_UNTIL.get(slug, 0.0), time.monotonic() + seconds + ECHO_SECONDS)


def is_quiet(slug: str) -> bool:
    return time.monotonic() < _QUIET_UNTIL.get(slug, 0.0)


def said_aloud(request: Request, slug: str, user_id: int, username: str, text: str, *, answer: str = "always", humans: int = 1) -> dict:
    """The words of a person are written in the room as theirs; then, if a virtual person is there and `answer` lets it (`always`; `named`: only when
    one is called by name or the person is alone with them; `never`), one answers, in the room and aloud, and a request to share the screen
    makes a slide. Blocking: run it in a thread. Returns what was written and who answered."""
    factory = request.app.state.session_factory
    with factory() as db:
        room = service.room_by_slug(db, slug)
        member = service.member_of(db, room.id, user_id) if room else None
        problem = service.posting_problem(room, member) if room else service.NOT_FOUND
        if room is None or problem is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, problem or service.NOT_FOUND)
        speakers = virtual_members(db, slug)
        message = Message(room_id=room.id, user_id=user_id, content=text[:2000])
        db.add(message)
        db.commit()
        emit(request, slug, MessageOut.model_validate(service.show_one(db, message)).frame())
        history = virtual_reply.history(db, slug)
    if not speakers or answer == "never":
        return {"text": text, "answered": ""}
    called = any(s[1].lower().replace("_", " ") in text.lower().replace("_", " ") or s[2].lower() in text.lower() for s in speakers)
    if answer == "named" and not (called or humans <= 1):
        return {"text": text, "answered": ""}
    speaker = who_answers(speakers, text, slug)
    uid, name = speaker[0], speaker[2]
    if STOP_SHARE.search(text):
        emit(request, slug, {"type": "slide", "user_id": uid, "name": name, "title": "", "lines": []})
        return {"text": text, "answered": name}
    if SHARE_ASK.search(text):
        emit(request, slug, {"type": "slide", "user_id": uid, "name": name, "title": text[:60], "lines": slide_of(text, uid, user_id)})
        return {"text": text, "answered": name}
    answer = virtual_reply.ask_agent_counted(uid, user_id, username, history) or virtual_reply.ask_agent_counted(uid, user_id, username, history)  # (once more: the model is sometimes slow)
    if answer is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The virtual person could not answer now")
    reply, counted = answer
    saved = virtual_reply.save(factory, slug, uid, speaker[1], reply)
    if saved is not None:
        emit(request, slug, saved.frame())
        told = virtual_reply.tell_usage(factory, slug, name, counted)
        if told is not None:
            emit(request, slug, told.frame())
    seconds = 0.0
    for frame in voice_frames(speaker, reply):
        emit(request, slug, frame)
        if frame["pcm"] and frame["rate"]:
            seconds += len(base64.b64decode(frame["pcm"])) / 2 / frame["rate"]
            mark_speaking(slug, seconds)
    return {"text": text, "answered": name}
