"""The lines of a room about what happens in it are said by `system`: its user id and name, and the person they are about in the content."""

from sn_shared import directory
from api.chat.social import models as social_models
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from api.chat import service
from api.chat.account_events import DELETED_USERNAME, on_user_deleted, on_user_renamed
from api.chat.db import Base, make_engine
from api.chat.main import create_app
from api.chat.models import Message, Room, RoomMember
from tests.chat.conftest import auth_cookie
from tests.chat.test_room_api import call, make


def lines(client, slug):
    return [m for m in call(client, "GET", f"/rooms/{slug}/messages").json() if m["kind"] == "system"]


def test_a_line_is_said_by_system_and_names_the_person_in_its_content(raw_client):
    slug = make(raw_client)["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/join", 2, "bob", json={})
    call(raw_client, "DELETE", f"/rooms/{slug}/members/2")
    said = lines(raw_client, slug)
    assert [(m["user_id"], m["username"], m["content"]) for m in said] == [
        (service.SYSTEM_USER_ID, "system", "joined:bob"),
        (service.SYSTEM_USER_ID, "system", "kicked:bob"),
    ]
    assert "room" not in said[0]  # the room of a message is the one it was asked of


def test_only_the_owner_deletes_a_line_of_the_system(raw_client):
    slug = make(raw_client)["slug"]
    call(raw_client, "POST", f"/rooms/{slug}/join", 2, "bob", json={})
    line = lines(raw_client, slug)[0]
    assert call(raw_client, "DELETE", f"/rooms/{slug}/messages/{line['id']}", 2, "bob").status_code == 403
    assert call(raw_client, "DELETE", f"/rooms/{slug}/messages/{line['id']}").status_code == 204
    assert lines(raw_client, slug) == []


def test_say_keeps_how_many_and_who_for_the_virtual_people(raw_client):
    slug = make(raw_client)["slug"]
    with raw_client.app.state.session_factory() as db:
        room = db.scalar(select(Room).where(Room.slug == slug))
        line = service.say(db, room, "virtual_added:4", 1)
        assert (line.user_id, line.username, line.content) == (-1, "system", "virtual_added:4:<1>")  # the id is kept, not the name
        assert line.shown_content == "virtual_added:4:alice"


def test_a_line_shows_the_name_the_person_has_now_and_an_old_line_keeps_its_name(raw_client):
    slug = make(raw_client)["slug"]
    with raw_client.app.state.session_factory() as db:
        room = db.scalar(select(Room).where(Room.slug == slug))
        old = service.say(db, room, "kicked", 1)
        legacy = Message(room_id=room.id, user_id=-1, content="kicked:bob")
        db.add(legacy)
        db.commit()
        db.execute(update(directory.Person).where(directory.Person.user_id == 1).values(username="alicia"))
        db.commit()
        shown = {row.id: row.shown_content for row in service.show(db, [old, legacy])}
        assert shown[old.id] == "kicked:alicia" and shown[legacy.id] == "kicked:bob"



def seeded():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    social_models.ensure_tables(engine)
    directory.ensure_table_for_sqlite(engine)
    db = sessionmaker(engine, expire_on_commit=False)()
    room = Room(slug="talk", title="talk", user_id=1)
    db.add(room)
    db.flush()
    for user_id, name in ((1, "alice"), (2, "bob_x")):
        db.add(directory.Person(user_id=user_id, username=name))
        db.add(RoomMember(room_id=room.id, user_id=user_id))
    db.add_all(
        [
            Message(room_id=room.id, user_id=-1, content="kicked:bob_x"),
            Message(room_id=room.id, user_id=-1, content="joined:alice"),
            Message(room_id=room.id, user_id=-1, content="virtual_added:2:bob_x"),
        ]
    )
    db.flush()
    return db


def test_a_rename_changes_nothing_in_the_lines(db=None):
    db = seeded()
    on_user_renamed(db, 2, "robert")
    db.flush()
    assert [m.content for m in db.scalars(select(Message).order_by(Message.id))] == ["kicked:bob_x", "joined:alice", "virtual_added:2:bob_x"]


def test_a_deleted_account_is_no_longer_named_in_the_lines():
    db = seeded()
    on_user_deleted(db, 2)
    db.flush()
    contents = [m.content for m in db.scalars(select(Message).order_by(Message.id))]
    assert contents == [f"kicked:{DELETED_USERNAME}", "joined:alice", f"virtual_added:2:{DELETED_USERNAME}"]  # `_` of a name is a letter, not a wildcard
