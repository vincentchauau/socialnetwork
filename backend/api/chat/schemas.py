from datetime import datetime
from typing import Literal

from api.chat.models import CARD_PREFIX
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

ROOM_PATTERN = r"^[A-Za-z0-9_-]{1,32}$"  # every slug, also the ones of rooms made before they had titles
NEW_SLUG_PATTERN = r"^[A-Za-z0-9_-]{3,32}$"  # a slug someone chooses
MAX_MESSAGE_LENGTH = 2000
MAX_CAPACITY = 200

Visibility = Literal["public", "private"]
JoinPolicy = Literal["open", "approval", "invite"]


class IncomingMessage(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    reply_to: int | None = Field(default=None, ge=1)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str
    kind: str = "text"
    content: str = Field(validation_alias=AliasChoices("shown_content", "content"))  # a system line with the name in it (see `service.show`)
    reply_to_id: int | None = None
    pinned_at: datetime | None = None
    edited_at: datetime | None = None
    created_at: datetime

    @field_validator("content")
    @classmethod
    def _without_the_card_mark(cls, value: str) -> str:
        """A card is kept with a mark in front (`CARD_PREFIX`) that nobody outside the chat needs: what is sent is the card itself."""
        return value[len(CARD_PREFIX):] if value.startswith(CARD_PREFIX) else value

    def frame(self) -> dict:
        """What the sockets of the room are told when this message is written or changed."""
        return {"type": "message", **self.model_dump(mode="json")}


MAX_AVATAR = 20000  # a small image kept inline (the browser shrinks it) fits
INLINE_PICTURE = ("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")


def _picture(value: str | None) -> str | None:
    """The address of a picture: empty, a path of this site, or http(s)."""
    if value is None or value == "":
        return value
    if value.startswith(INLINE_PICTURE):
        return value
    if not (value.startswith("/") and not value.startswith("//")) and not value.startswith(("https://", "http://")):
        raise ValueError("The picture is an address that starts with / or https://, or a small image")
    return value


class _RoomFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    category: str = Field(default="", max_length=32)
    avatar: str = Field(default="", max_length=MAX_AVATAR)
    visibility: Visibility = "public"
    join_policy: JoinPolicy = "open"
    capacity: int = Field(default=MAX_CAPACITY, ge=2, le=MAX_CAPACITY)

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, value: str) -> str:
        return _picture(value) or ""

    @field_validator("title", "category", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _policy(self):
        if self.join_policy == "invite":
            raise ValueError("A room is joined openly or with approval")
        if self.visibility == "private" and self.join_policy == "open":
            raise ValueError("A private room is joined with an invitation or approval, not openly")
        return self


class RoomCreate(_RoomFields):
    slug: str | None = Field(default=None, pattern=NEW_SLUG_PATTERN)  # made from the title when left out (not `dm-…`: that is a chat of two)

    @field_validator("slug")
    @classmethod
    def _not_a_chat_of_two(cls, value):
        if value is not None and value.startswith("dm-"):
            raise ValueError("An address that starts with dm- is for a chat of two")
        return value


class RoomUpdate(BaseModel):
    """Only what is sent changes."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = Field(default=None, max_length=32)
    avatar: str | None = Field(default=None, max_length=MAX_AVATAR)
    visibility: Visibility | None = None
    join_policy: JoinPolicy | None = None
    capacity: int | None = Field(default=None, ge=2, le=MAX_CAPACITY)
    state: Literal["open", "closed"] | None = None

    @field_validator("avatar")
    @classmethod
    def _avatar(cls, value: str | None) -> str | None:
        return _picture(value)

    @field_validator("join_policy")
    @classmethod
    def _not_by_invitation(cls, value):
        if value == "invite":
            raise ValueError("A room is joined openly or with approval")
        return value


class DmCreate(BaseModel):
    user_id: int = Field(ge=1)


class MemberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["joined", "banned"] | None = None  # approve a request, ban, or lift a ban
    reason: str | None = Field(default=None, max_length=200)  # kept with a ban
    muted: bool | None = None  # may read and not write (or may write again)


class ReadBody(BaseModel):
    message_id: int = Field(ge=1)


class TransferBody(BaseModel):
    user_id: int = Field(ge=1)


class MyMembership(BaseModel):
    role: str  # owner | member
    status: str
    muted: bool = False
    unread: int = 0
    notify: bool = True  # False: the room is quiet, no badge of unread messages
    last_read: int = 0  # the newest message I had read up to


class MessageHit(BaseModel):
    id: int
    username: str
    content: str  # the part of the message around what was searched for


class SearchHit(BaseModel):
    """Why a room is in the result of a search: where the words were found."""

    fields: list[str] = []  # of title, slug, category
    members: list[str] = []  # usernames of members that contain the words (a few)
    message: MessageHit | None = None  # the latest message that contains them


class LastMessage(BaseModel):
    username: str
    kind: str
    content: str  # a line of it
    at: datetime


class RoomOut(BaseModel):
    id: int
    slug: str
    kind: str
    title: str
    category: str
    avatar: str = ""  # its picture (a chat of two: the other person's)
    user_id: int  # the owner
    owner_name: str = ""  # the name of the owner, for the tables
    visibility: str
    join_policy: str
    capacity: int
    state: str  # open | closed | deleted (hidden; only its owner still sees it)
    members: int  # joined members
    online: int = 0  # members with a socket open now
    me: MyMembership | None = None
    hit: SearchHit | None = None  # set when the list was searched
    last_message: LastMessage | None = None  # set in the lists of my rooms: what was said last


class PersonOut(BaseModel):
    user_id: int
    username: str
    online: bool


class MemberOut(BaseModel):
    user_id: int
    username: str
    role: str  # owner | member
    status: str
    muted: bool = False
    name: str = ""  # the name of the person, as the profile lets the viewer read it (a virtual person: always)
    avatar: str = ""  # their picture, the same way
    online: bool = False
    virtual: bool = False  # made by the platform (always there: they answer when somebody writes)
    status_reason: str | None = None  # why they were sent away: only for the owner


