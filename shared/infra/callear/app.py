"""The ear of the calls. The chat tells it, with a signed call, which room to listen to:

  POST /watch {room, slug}    join that LiveKit room as a hidden listener (it is not seen, and it says nothing)

It hears every person who speaks, cuts what each says into utterances by the pauses, and sends each to the chat (`POST <CHAT_INTERNAL_URL>/internal/call-heard`,
signed), which makes it into words and writes it in the room as that person's message. It leaves when nobody is left in the room, so a room is not kept
open by its listener.
"""

import array
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import time

import httpx
from fastapi import FastAPI, HTTPException, Request, status
from livekit import rtc

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("callear")

SECRET = os.environ.get("CALLEAR_SECRET", "")
KEY, LIVEKIT_SECRET = os.environ.get("LIVEKIT_API_KEY", ""), os.environ.get("LIVEKIT_API_SECRET", "")
LIVEKIT = os.environ.get("LIVEKIT_INTERNAL_URL", "ws://livekit:7880")
CHAT = os.environ.get("CHAT_INTERNAL_URL", "").rstrip("/")  # e.g. http://api-backend:8000/chat
MIN_SECRET_CHARS = 16
MAX_SKEW_SECONDS = 60
RATE = 16000
SILENCE_LEVEL = 0.01  # of full scale: below this nobody is talking
END_OF_TALK = 1.0  # seconds of quiet that end an utterance
LEAST_TALK = 0.7  # shorter than this is a noise
MOST_TALK = 25.0
ALONE_SECONDS = 30  # nobody else in the room for this long: the ear leaves
MAX_ROOMS = 8
SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

app = FastAPI(title="socialnetwork callear")
watching: dict[str, asyncio.Task] = {}


def digest(timestamp: str, scope: str, body: bytes) -> str:
    return hmac.new(SECRET.encode(), timestamp.encode() + b"." + scope.encode() + b"." + body, hashlib.sha256).hexdigest()


def sign(scope: str, body: bytes) -> dict[str, str]:
    stamp = str(int(time.time()))
    return {"X-Service-Timestamp": stamp, "X-Service-Signature": digest(stamp, scope, body)}


def b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def ticket(room: str) -> str:
    """The ticket of the ear: it listens and does not publish, and it is not shown to the others (a hidden participant)."""
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    body = b64(json.dumps({
        "iss": KEY, "sub": "ear", "name": "ear", "nbf": now - 5, "exp": now + 4 * 3600,
        "video": {"room": room, "roomJoin": True, "canSubscribe": True, "canPublish": False, "canPublishData": False, "hidden": True},
    }).encode())
    return (head + b"." + body + b"." + b64(hmac.new(LIVEKIT_SECRET.encode(), head + b"." + body, hashlib.sha256).digest())).decode()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/watch", status_code=status.HTTP_202_ACCEPTED)
async def watch(request: Request) -> dict:
    raw = await request.body()
    stamp, given = request.headers.get("X-Service-Timestamp", ""), request.headers.get("X-Service-Signature", "")
    try:
        fresh = abs(time.time() - int(stamp)) <= MAX_SKEW_SECONDS
    except ValueError:
        fresh = False
    if len(SECRET) < MIN_SECRET_CHARS or not fresh or not hmac.compare_digest(digest(stamp, "POST /watch", raw), given):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed")
    try:
        body = json.loads(raw)
        room, slug = str(body["room"]), str(body["slug"])[:64]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid request") from None
    if not room or len(room) > 64 or not set(room) <= SAFE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bad room")
    current = watching.get(room)
    if current is not None and not current.done():
        return {"watching": True}
    if len([task for task in watching.values() if not task.done()]) >= MAX_ROOMS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many calls")
    watching[room] = asyncio.create_task(listen(room, slug))
    return {"watching": True}


def level_of(samples: array.array) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768


async def hear_person(room: rtc.Room, slug: str, track: rtc.Track, identity: str, client: httpx.AsyncClient) -> None:
    """One person's microphone: cut into utterances by the pauses, each sent to the chat as it ends."""
    stream = rtc.AudioStream(track, sample_rate=RATE, num_channels=1)
    pending = bytearray()
    talking = False
    quiet = 0.0
    try:
        async for event in stream:
            frame = event.frame
            samples = array.array("h", bytes(frame.data))
            seconds = len(samples) / RATE
            if level_of(samples) > SILENCE_LEVEL:
                talking = True
                quiet = 0.0
                pending += samples.tobytes()
            elif talking:
                quiet += seconds
                pending += samples.tobytes()
            if talking and (quiet >= END_OF_TALK or len(pending) / 2 / RATE >= MOST_TALK):
                utterance = bytes(pending)
                pending.clear()
                talking = False
                quiet = 0.0
                if len(utterance) / 2 / RATE >= LEAST_TALK:
                    humans = max(1, len(room.remote_participants))
                    asyncio.create_task(send(client, slug, identity, utterance, humans))
    finally:
        await stream.aclose()


async def send(client: httpx.AsyncClient, slug: str, identity: str, utterance: bytes, humans: int) -> None:
    if not CHAT or not identity.isdigit():
        return
    payload = json.dumps({"slug": slug, "identity": int(identity), "pcm": base64.b64encode(utterance).decode(), "rate": RATE, "humans": humans}).encode()
    log.info("%s: heard %.1fs from %s", slug, len(utterance) / 2 / RATE, identity)
    try:
        await client.post(f"{CHAT}/internal/call-heard", content=payload, headers={"Content-Type": "application/json", **sign("POST /internal/call-heard", payload)})
    except httpx.HTTPError:
        log.warning("the chat did not take what was heard in %s", slug)


async def listen(name: str, slug: str) -> None:
    room = rtc.Room()
    tasks: dict[str, asyncio.Task] = {}
    async with httpx.AsyncClient(timeout=60) as client:

        @room.on("track_subscribed")
        def subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO and publication.source == rtc.TrackSource.SOURCE_MICROPHONE:
                tasks[publication.sid] = asyncio.create_task(hear_person(room, slug, track, participant.identity, client))

        @room.on("track_unsubscribed")
        def unsubscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant) -> None:
            task = tasks.pop(publication.sid, None)
            if task is not None:
                task.cancel()

        try:
            await room.connect(LIVEKIT, ticket(name))
            log.info("listening to the call of %s", slug)
            alone = 0.0
            while room.isconnected():
                await asyncio.sleep(2)
                alone = 0.0 if room.remote_participants else alone + 2
                if alone >= ALONE_SECONDS:
                    break
        except Exception:  # noqa: BLE001 - a call that cannot be joined is not listened to
            log.warning("could not listen to the call of %s", slug, exc_info=True)
        finally:
            for task in tasks.values():
                task.cancel()
            await room.disconnect()
            watching.pop(name, None)
            log.info("stopped listening to the call of %s", slug)
