"""Idempotent upgrade of a chat database made by an earlier version (there is no migration framework in this repo).

`Base.metadata.create_all` makes the missing tables but never alters a table that is there, so this does:
- a database from before rooms existed: the rooms that old messages name are made (each distinct `messages.room` becomes a public room
  whose members are the people who wrote in it);
- a database with the wider tables of the version before this one: what lived in a column that is gone is folded into the ones that stay
  (the owner is `rooms.owner_id`, now `rooms.user_id`; a mute is a joined member with the reason `muted`; a card is a message that starts
  with `CARD_PREFIX`), then those columns are dropped (`LEGACY_COLUMNS`).
Safe to run on every start; portable to SQLite and PostgreSQL (SQLite cannot drop a column that is indexed or unique: it is left, unused).
"""

import logging

from sn_shared.db import add_column_sql
from sqlalchemy import BigInteger, Boolean, DateTime, Engine, String, inspect, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeEngine

from api.chat.models import CARD_PREFIX, MUTED_REASON, Room, RoomMember
from api.chat.service import now

log = logging.getLogger(__name__)

# per table: (name, type, NOT NULL default literal or None for a nullable column)
_COLUMNS: dict[str, tuple[tuple[str, TypeEngine, str | None], ...]] = {
    "messages": (
        ("room_id", BigInteger(), None),
        ("reply_to_id", BigInteger(), None),
        ("pinned_at", DateTime(timezone=True), None),
        ("deleted_at", DateTime(timezone=True), None),
        ("edited_at", DateTime(timezone=True), None),
    ),
    "rooms": (("avatar", String(255), "''"),),
    "room_members": (
        ("status_reason", String(200), "''"),
        ("hidden_at", DateTime(timezone=True), None),
        ("notify", Boolean(), "TRUE"),
    ),
}
# the columns of the version before this one that are gone (the data they held is folded first: see `fold_legacy`)
LEGACY_COLUMNS: dict[str, tuple[str, ...]] = {
    "rooms": ("description", "region", "post_policy", "opens_at", "closes_at", "dm_key", "settings", "created_by", "created_at", "closed_at", "deleted_at", "last_message_at"),
    "room_members": ("role", "muted_until", "joined_at", "left_at", "kicked_at"),
    "messages": ("kind",),
}
# (constraint, table, column, referenced table): added where the database can (PostgreSQL), after orphans are cleared
FOREIGN_KEYS = (
    ("fk_messages_room_id", "messages", "room_id", "rooms"),
    ("fk_messages_reply_to_id", "messages", "reply_to_id", "messages"),
    ("fk_meetings_room_id", "meetings", "room_id", "rooms"),
)
ROOM_COLUMN_DEFAULTS = {"kind": "chat", "visibility": "public", "join_policy": "open"}


def _columns(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)} if table in inspect(engine).get_table_names() else set()


def ensure_columns(engine: Engine) -> list[str]:
    """Add the columns the tables gained; returns `table.column` of each one added."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    added: list[str] = []
    with engine.begin() as connection:
        for table, columns in _COLUMNS.items():
            if table not in tables:
                continue
            have = {column["name"] for column in inspector.get_columns(table)}
            for name, type_, default in columns:
                if name not in have:
                    connection.execute(text(add_column_sql(engine, table, name, type_, default)))
                    added.append(f"{table}.{name}")
        if "messages" in tables and "room_id" not in {c["name"] for c in inspector.get_columns("messages")}:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_room_ref ON messages (room_id, id)"))
    return added


def rename_owner_column(engine: Engine) -> bool:
    """The owner of a room was `rooms.owner_id`: it is `rooms.user_id` now. True when it was renamed."""
    have = _columns(engine, "rooms")
    if "owner_id" not in have or "user_id" in have:
        return False
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS ix_rooms_owner"))
        connection.execute(text("ALTER TABLE rooms RENAME COLUMN owner_id TO user_id"))
    return True


def rename_meeting_room_column(engine: Engine) -> bool:
    """The name of the room of a meeting at the video server was `meetings.jitsi_room`: it is `meetings.room_name` now. True when renamed."""
    have = _columns(engine, "meetings")
    if "jitsi_room" not in have or "room_name" in have:
        return False
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE meetings RENAME COLUMN jitsi_room TO room_name"))
    return True


def ensure_foreign_keys(engine: Engine) -> list[str]:
    """The references between tables the database can enforce; a column that points at nothing is left alone (and logged)."""
    if engine.dialect.name != "postgresql":
        return []
    added: list[str] = []
    inspector = inspect(engine)
    with engine.begin() as connection:
        # `room_members` came with `ON DELETE CASCADE`: nothing is removed with a room now (only the owner's purge, in code).
        for fk in inspector.get_foreign_keys("room_members"):
            if fk["constrained_columns"] == ["room_id"] and (fk.get("options") or {}).get("ondelete") == "CASCADE":
                connection.execute(text(f"ALTER TABLE room_members DROP CONSTRAINT {fk['name']}"))
                connection.execute(text(f"ALTER TABLE room_members ADD CONSTRAINT {fk['name']} FOREIGN KEY (room_id) REFERENCES rooms (id)"))
                added.append(fk["name"])
        for name, table, column, target in FOREIGN_KEYS:
            if table not in inspector.get_table_names() or any(column in fk["constrained_columns"] for fk in inspector.get_foreign_keys(table)):
                continue
            if table == target:  # a reply to a message that is gone stands on its own
                connection.execute(text(f"UPDATE {table} SET {column} = NULL WHERE {column} IS NOT NULL AND {column} NOT IN (SELECT id FROM {target})"))
            orphans = connection.scalar(text(f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL AND {column} NOT IN (SELECT id FROM {target})"))
            if orphans:
                log.warning("%s.%s: %s rows point at nothing, no foreign key added", table, column, orphans)
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}) REFERENCES {target} (id)"))
            added.append(name)
    return added


def migrate_statuses(session: Session) -> None:
    """`active` members are `joined` now; a room joined by invitation is joined with approval."""
    session.execute(update(RoomMember).where(RoomMember.status == "active").values(status="joined"))
    session.execute(text("UPDATE rooms SET join_policy = 'approval' WHERE kind = 'chat' AND join_policy = 'invite'"))


def has_room_column(session: Session) -> bool:
    return "room" in {column["name"] for column in inspect(session.get_bind()).get_columns("messages")}


def backfill_rooms(session: Session) -> int:
    """Make a room for every name old messages use, then point those messages at it; returns the rooms made. Old messages name their room
    in a column `room` that is dropped afterwards (`drop_room_column`), so this reads it with plain SQL, and only while it is there."""
    if not has_room_column(session):
        return 0
    names = session.execute(text("SELECT DISTINCT room FROM messages WHERE room_id IS NULL")).scalars().all()
    made = 0
    for name in names:
        room = session.scalar(select(Room).where(Room.slug == name))
        if room is None:
            first = session.execute(text("SELECT user_id FROM messages WHERE room = :n AND user_id > 0 ORDER BY id LIMIT 1"), {"n": name}).scalar()
            room = Room(slug=name, title=name, user_id=first or 0, **ROOM_COLUMN_DEFAULTS)
            session.add(room)
            session.flush()
            made += 1
            writers = session.execute(text("SELECT user_id, MAX(id) FROM messages WHERE room = :n AND user_id > 0 GROUP BY user_id"), {"n": name}).all()
            for user_id, _newest_id in writers:
                session.add(RoomMember(room_id=room.id, user_id=user_id, status="joined"))
        session.execute(text("UPDATE messages SET room_id = :r WHERE room = :n AND room_id IS NULL"), {"r": room.id, "n": name})
    return made


def drop_room_column(engine: Engine) -> bool:
    """The room of a message is its `room_id`: the column that held the slug (and the index on it) goes. True when it was there."""
    if "room" not in {column["name"] for column in inspect(engine).get_columns("messages")}:
        return False
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX IF EXISTS ix_messages_room_id"))
        connection.execute(text("ALTER TABLE messages DROP COLUMN room"))
    return True


def fold_legacy(engine: Engine) -> None:
    """What the columns that are going held, put where it lives now: a mute still running becomes the reason `muted` of a joined member, a card
    becomes a message that starts with `CARD_PREFIX`."""
    with engine.begin() as connection:
        if "muted_until" in _columns(engine, "room_members"):
            connection.execute(
                text("UPDATE room_members SET status_reason = :muted WHERE status = 'joined' AND muted_until IS NOT NULL AND muted_until > :now"),
                {"muted": MUTED_REASON, "now": now()},
            )
        if "kind" in _columns(engine, "messages"):
            connection.execute(
                text("UPDATE messages SET content = :prefix || content WHERE kind = 'card' AND content NOT LIKE :like"),
                {"prefix": CARD_PREFIX, "like": CARD_PREFIX + "%"},
            )


def drop_legacy_columns(engine: Engine) -> list[str]:
    """Drop the columns of `LEGACY_COLUMNS` that are still there; returns `table.column` of each one dropped. The two indexes of `rooms` go first and
    are made again (they held columns that are gone)."""
    dropped: list[str] = []
    with engine.begin() as connection:
        for index in ("ix_rooms_owner", "ix_rooms_listing"):
            connection.execute(text(f"DROP INDEX IF EXISTS {index}"))
    for table, names in LEGACY_COLUMNS.items():
        have = _columns(engine, table)
        for name in names:
            if name not in have:
                continue
            try:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {name}"))
                dropped.append(f"{table}.{name}")
            except Exception:  # noqa: BLE001 - SQLite cannot drop a unique or indexed column: it stays, unused
                log.warning("%s.%s could not be dropped", table, name)
    if "rooms" in inspect(engine).get_table_names():
        with engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_rooms_listing ON rooms (kind, visibility, state, category)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_rooms_user ON rooms (user_id)"))
    return dropped


def relax_unused_columns(engine: Engine) -> bool:
    """`room_members.attributes` is no longer written (the model dropped it) but an old PostgreSQL table has it NOT NULL with no default: new members
    would fail to insert. True when the constraint was lifted. (The column itself is for the owner of the database to drop.)"""
    if engine.dialect.name != "postgresql" or "room_members" not in inspect(engine).get_table_names():
        return False
    attributes = next((c for c in inspect(engine).get_columns("room_members") if c["name"] == "attributes"), None)
    if attributes is None or attributes["nullable"]:
        return False
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE room_members ALTER COLUMN attributes DROP NOT NULL"))
    return True


def widen_avatar(engine: Engine) -> bool:
    """`rooms.avatar` holds a small image now, not only an address: PostgreSQL's varchar(255) becomes text. True when widened."""
    if engine.dialect.name != "postgresql" or "avatar" not in _columns(engine, "rooms"):
        return False
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE rooms ALTER COLUMN avatar TYPE TEXT"))
    return True


def upgrade(engine: Engine, session_factory) -> None:
    rename_owner_column(engine)
    rename_meeting_room_column(engine)
    ensure_columns(engine)
    widen_avatar(engine)
    relax_unused_columns(engine)
    with session_factory() as session:
        backfill_rooms(session)
        session.flush()
        migrate_statuses(session)
        session.commit()
    drop_room_column(engine)
    fold_legacy(engine)
    drop_legacy_columns(engine)
    ensure_foreign_keys(engine)
