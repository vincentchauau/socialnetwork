"""Commands of the owner in the box of a room: `/owner bob`, `/mute bob`, `/unmute bob`, `/kick bob`, `/ban bob`, `/unban bob`, `/close`, `/reopen`.

They do what the buttons of the row do, through the same routes (so the same rules, lines and events), as the person who wrote the line:
nobody but the owner gets further than the route lets them."""

import re
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select

PERSON_COMMANDS = {"owner", "mute", "unmute", "kick", "ban", "unban"}
ROOM_COMMANDS = {"close", "reopen"}
USAGE = "Owner commands: /owner <name>, /mute <name>, /unmute <name>, /kick <name>, /ban <name>, /unban <name>, /close, /reopen"


def parse(content: str) -> tuple[str, str] | None:
    """The command and the name of a line like `/mute bob` (the name is empty for /close and /reopen), or None when it is not one of these."""
    word, _, rest = content[1:].partition(" ") if content.startswith("/") else ("", "", "")
    command = word.lower()
    if command in ROOM_COMMANDS and not rest.strip():
        return command, ""
    if command in PERSON_COMMANDS and rest.strip():
        return command, rest.strip().lstrip("@")
    return (command, "") if command in PERSON_COMMANDS | ROOM_COMMANDS else None


TAIL = r"[\s,.!?]*(?:đi|nhé|nha|nhỉ|giúp tôi|giúp mình|please)?[\s,.!?]*$"
_SAYINGS: tuple[tuple[str, str], ...] = (  # (command, what the line looks like; group 1 is the name), the longer ones first
    ("owner", r"^(?:chuyển|đổi|giao|trao)\s+(?:quyền\s+)?(?:owner|chủ phòng|chủ)\s+(?:cho|sang)\s+(.+?)"),
    ("owner", r"^(?:đặt|cho)\s+(.+?)\s+(?:làm|là)\s+(?:owner|chủ phòng|chủ)"),
    ("owner", r"^(?:make|set)\s+(.+?)\s+(?:the\s+)?owner"),
    ("owner", r"^(?:transfer|give|hand)\s+(?:the\s+)?(?:owner(?:ship)?|room)\s+to\s+(.+?)"),
    ("unmute", r"^(?:bật tiếng|unmute)\s+(.+?)"),
    ("mute", r"^(?:tắt tiếng|mute)\s+(.+?)"),
    ("unban", r"^(?:bỏ cấm|unban)\s+(.+?)"),
    ("ban", r"^(?:cấm|ban)\s+(.+?)"),
    ("kick", r"^(?:mời|đuổi)\s+(.+?)\s+ra(?:\s+khỏi phòng)?"),
    ("kick", r"^(?:đuổi|kick)\s+(.+?)"),
    ("close", r"^(?:đóng phòng|close(?: the)? room)()"),
    ("reopen", r"^(?:mở lại phòng|reopen(?: the)? room)()"),
)


def parse_saying(content: str) -> tuple[str, str] | None:
    """The command of a line written as people talk (`chuyển owner cho Giang Le`, `mute bob`, `đóng phòng`), or None. The owner only: the caller checks."""
    if content.startswith("/") or len(content) > 120:
        return None
    for command, pattern in _SAYINGS:
        found = re.match(pattern + TAIL, content.strip(), re.IGNORECASE)
        if found:
            return command, found.group(1).strip().lstrip("@")
    return None


def same_room_commands(wanted: str, person: dict[str, Any]) -> bool:
    """A name as written (`Giang Le`, `giang_le`, `@Giang_Le`) is the username or the name of the person."""
    key = lambda text: re.sub(r"[\s_]+", " ", str(text)).strip().lower()  # noqa: E731
    return key(wanted) in (key(person["username"]), key(person.get("name") or ""))


def owns(factory, slug: str, user_id: int) -> bool:
    from api.chat.models import Room

    with factory() as db:
        room = db.scalar(select(Room).where(Room.slug == slug))
        return room is not None and room.user_id == user_id


def detail_room_commands(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail") or "That could not be done")
    except ValueError:
        return "That could not be done"


async def run(app: FastAPI, slug: str, cookies: dict[str, str], origin: str, command: str, name: str) -> str | None:
    """Do the command as the person whose cookies these are (from the origin their socket was accepted from); returns what went wrong (as the server words it), or None when it is done."""
    if command in PERSON_COMMANDS and not name:
        return USAGE
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://chat", cookies=cookies, headers={"Origin": origin}) as client:
        if command in ROOM_COMMANDS:
            done = await client.patch(f"/rooms/{slug}", json={"state": "closed" if command == "close" else "open"})
            return None if done.is_success else detail_room_commands(done)
        found = await client.get(f"/rooms/{slug}/members")
        if not found.is_success:
            return detail_room_commands(found)
        people: list[dict[str, Any]] = [m for m in found.json() if same_room_commands(name, m)]
        if not people:
            return f"{name} is not in this room"
        user_id = people[0]["user_id"]
        member = f"/rooms/{slug}/members/{user_id}"
        done = {
            "owner": lambda: client.post(f"/rooms/{slug}/transfer", json={"user_id": user_id}),
            "mute": lambda: client.patch(member, json={"muted": True}),
            "unmute": lambda: client.patch(member, json={"muted": False}),
            "kick": lambda: client.delete(member),
            "ban": lambda: client.patch(member, json={"status": "banned"}),
            "unban": lambda: client.patch(member, json={"status": "joined"}),
        }[command]
        response = await done()
        return None if response.is_success else detail_room_commands(response)
