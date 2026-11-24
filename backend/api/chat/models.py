from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, case, true
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from datetime import datetime

from api.chat.db import Base
from sn_shared.clock import utcnow

SYSTEM_USER_ID = -1  # the account `system` of center: it says what happens in a room, and nobody signs in as it
CARD_PREFIX = "\x1ecard:"  # a message whose content starts with this holds a card (JSON) said by a virtual person or by `system`


class Room(Base):
    """A chat room. `kind` is `chat` (anyone can make one) or `dm` (two people, made by `POST /dm`; its slug is `dm-<low>-<high>`).
    `user_id` is its owner (who made it, or whom it was handed to)."""

    __tablename__ = "rooms"
    __table_args__ = (Index("ix_rooms_listing", "kind", "visibility", "state", "category"), Index("ix_rooms_user", "user_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)  # the address of the room: /chatwork#room=<slug>
    kind: Mapped[str] = mapped_column(String(8), default="chat", server_default="chat")
    title: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(32), default="", server_default="")  # a free label: "residents", "garage sale"…
    avatar: Mapped[str] = mapped_column(Text, default="", server_default="")  # its picture: an address, or a small image inline ("" for none)
    user_id: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str] = mapped_column(String(8), default="public", server_default="public")  # public | private
    join_policy: Mapped[str] = mapped_column(String(8), default="open", server_default="open")  # open (Public) | approval (Private) | invite (a chat of two)
    capacity: Mapped[int] = mapped_column(Integer, default=200, server_default="200")
    state: Mapped[str] = mapped_column(String(8), default="open", server_default="open")  # open | closed | deleted (hidden, never removed)


class RoomMember(Base):
    """Who belongs to a room. `user_id` is the id in center's `users` (no foreign key: another database). The owner is `Room.user_id`."""

    __tablename__ = "room_members"
    __table_args__ = (Index("ix_room_members_user", "user_id", "status"),)

    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(8), default="joined", server_default="joined")  # pending | joined | left | kicked | banned (the row stays)
    status_reason: Mapped[str] = mapped_column(String(200), default="", server_default="")  # why (a ban); `muted` on a joined member: they read, they do not write
    last_read_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notify: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())  # False: no badge of unread messages
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # taken off my list of past rooms (the row stays)

    @property
    def muted(self) -> bool:
        return self.status == "joined" and self.status_reason == MUTED_REASON


MUTED_REASON = "muted"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_room_ref", "room_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer)  # -1: the lines `system` says
    content: Mapped[str] = mapped_column(Text)  # a line of `system` is `<what>:<<user id>>`; a card starts with CARD_PREFIX
    reply_to_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # set when the author changed the text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @hybrid_property
    def kind(self) -> str:  # type: ignore[override]
        """`system` (said by the account `system`), `card` (starts with CARD_PREFIX) or `text`: worked out, not stored."""
        if (self.content or "").startswith(CARD_PREFIX):
            return "card"
        return "system" if self.user_id == SYSTEM_USER_ID else "text"

    @kind.expression
    def kind(cls):  # noqa: N805
        return case((cls.content.startswith(CARD_PREFIX, autoescape=True), "card"), (cls.user_id == SYSTEM_USER_ID, "system"), else_="text")


class Meeting(Base):
    """One video call of a room (a LiveKit room). Open while `ended_at` is empty; a room has one open meeting at a time."""

    __tablename__ = "meetings"
    __table_args__ = (Index("ix_meetings_room_open", "room_id", "ended_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    room_name: Mapped[str] = mapped_column(String(64))  # a name nobody can guess, given to the members of the room only
    started_by: Mapped[int] = mapped_column(Integer)  # 0 once the account is gone
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
