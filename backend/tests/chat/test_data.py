from datetime import UTC, datetime

from api.chat.models import Message, Room, RoomMember
from api.chat.social import models as social
from tests.chat.conftest import auth_cookie

ALICE = auth_cookie(1, "alice")
BOB = auth_cookie(2, "bob")


def seed(client):
    with client.app.state.session_factory() as db:
        mine = Room(slug="mine", title="Mine", user_id=1)
        theirs = Room(slug="theirs", title="Theirs", user_id=2)
        left = Room(slug="left", title="Left", user_id=2)
        db.add_all([mine, theirs, left])
        db.flush()
        db.add_all([
            RoomMember(room_id=mine.id, user_id=1), RoomMember(room_id=mine.id, user_id=2, status_reason="why"),
            RoomMember(room_id=theirs.id, user_id=2),
            RoomMember(room_id=left.id, user_id=1, status="left"), RoomMember(room_id=left.id, user_id=2),
        ])
        db.add_all([
            Message(room_id=mine.id, user_id=2, content="hello"),
            Message(room_id=mine.id, user_id=2, content="gone", deleted_at=datetime.now(UTC)),
            Message(room_id=theirs.id, user_id=2, content="private"),
            Message(room_id=left.id, user_id=2, content="after I left"),
        ])
        db.add_all([
            social.Edge(src_id=1, dst_id=2, kind="block"), social.Edge(src_id=2, dst_id=1, kind="block"),
            social.Notification(user_id=1, kind="friend_request"), social.Notification(user_id=2, kind="friend_request"),
            social.Report(reporter_id=1, target_type="user", target_id="2", reason="spam"),
            social.Report(reporter_id=2, target_type="user", target_id="1", reason="spam"),
        ])
        db.commit()
        return {"mine": mine.id, "theirs": theirs.id, "left": left.id}


def test_anonymous_is_401(raw_client):
    assert raw_client.get("/records/tables").status_code == 401
    assert raw_client.get("/records/rooms").status_code == 401


def test_every_table_is_read_only(raw_client):
    seed(raw_client)
    tables = {t["name"]: t["writable"] for t in raw_client.get("/records/tables", headers=ALICE).json()}
    assert tables == {name: name in ("edges", "reports", "notifications", "meetings") for name in (
        "rooms", "room_members", "messages", "edges", "reports", "notifications", "meetings")}
    for name in tables:
        # a table with no owner refuses writes (405); a table with an owner checks the values (422) or the row (404)
        assert raw_client.post(f"/records/{name}", json={"values": {}}, headers=ALICE).status_code in (405, 422)
        assert raw_client.patch(f"/records/{name}/1", json={"values": {}}, headers=ALICE).status_code in (200, 404, 405)
        assert raw_client.delete(f"/records/{name}/1", headers=ALICE).status_code in (204, 404, 405)


def test_rooms_are_the_joined_ones(raw_client):
    ids = seed(raw_client)
    rows = raw_client.get("/records/rooms", headers=ALICE).json()["rows"]
    assert [r["slug"] for r in rows] == ["mine"]
    assert "settings" not in rows[0]
    assert raw_client.get(f"/records/rooms/{ids['mine']}", headers=ALICE).status_code == 200
    assert raw_client.get(f"/records/rooms/{ids['theirs']}", headers=ALICE).status_code == 404
    assert raw_client.get(f"/records/rooms/{ids['left']}", headers=ALICE).status_code == 404  # no longer joined


def test_members_and_messages_of_joined_rooms_only(raw_client):
    ids = seed(raw_client)
    members = raw_client.get("/records/room_members", headers=ALICE).json()["rows"]
    assert {(m["room_id"], m["user_id"]) for m in members} == {(ids["mine"], 1), (ids["mine"], 2)}
    assert all("status_reason" not in m for m in members)
    assert raw_client.get(f"/records/room_members/{ids['theirs']}~2", headers=ALICE).status_code == 404
    messages = raw_client.get("/records/messages", headers=ALICE).json()["rows"]
    assert [m["content"] for m in messages] == ["hello"]  # not deleted, not other rooms
    bobs = raw_client.get("/records/messages", headers=BOB).json()["rows"]
    assert {m["content"] for m in bobs} == {"hello", "private", "after I left"}


def test_social_rows_are_mine_only(raw_client):
    seed(raw_client)
    edges = raw_client.get("/records/edges", headers=ALICE).json()["rows"]
    assert [(e["src_id"], e["dst_id"]) for e in edges] == [(1, 2)]
    assert raw_client.get("/records/edges/2~1~block", headers=ALICE).status_code == 404
    notes = raw_client.get("/records/notifications", headers=ALICE).json()["rows"]
    assert [n["user_id"] for n in notes] == [1]
    reports = raw_client.get("/records/reports", headers=ALICE).json()["rows"]
    assert [r["reporter_id"] for r in reports] == [1]
