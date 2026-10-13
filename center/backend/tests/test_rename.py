"""POST /auth/me/username: policy, limits, reservation, session handling, notice, event."""

import json
from datetime import timedelta

import fakeredis
import pytest
from sqlalchemy import select

from app import usernames
from app.events import EventRelay
from app.models import AccountEvent, ReservedUsername, UserSession, utcnow
from sn_shared import COOKIE_NAME, decode_token
from tests.helpers import CREDS, STRONG, csrf, grant_fresh, register
from tests.mail_helpers import last_mail, sent_to, set_user, user_row, verified_account

PW = CREDS["password"]


def rename(client, session, username="bobby", password=PW):
    body = {"username": username}
    if password is not None:
        body["password"] = password
    return client.post("/auth/me/username", json=body, headers=csrf(session))


def events(client):
    with client.app.state.session_factory() as db:
        return list(db.scalars(select(AccountEvent).order_by(AccountEvent.id)))


def reservations(client):
    with client.app.state.session_factory() as db:
        return {r.username: r for r in db.scalars(select(ReservedUsername))}


def allow_rename_again(client, username):
    set_user(client, username, username_changed_at=utcnow() - timedelta(days=31))


def expire_reservation(client, name):
    with client.app.state.session_factory() as db:
        db.get(ReservedUsername, name).until = utcnow() - timedelta(minutes=1)
        db.commit()


def test_rename_returns_a_new_session_with_the_new_name(client):
    session = register(client)
    response = rename(client, session, "bobby")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "bobby" and body["id"] == session["id"] and body["role"] == "user"
    assert body["csrf_token"] != session["csrf_token"]
    assert decode_token(client.cookies.get(COOKIE_NAME)).username == "bobby"
    me = client.get("/auth/me").json()
    assert me["username"] == "bobby" and me["username_changed_at"] and me["can_rename_after"]
    assert client.post("/auth/login", json={"username": "bobby", "password": PW}).status_code == 200
    assert client.post("/auth/login", json=CREDS).status_code == 401


def test_me_fields_before_any_rename(client):
    register(client)
    me = client.get("/auth/me").json()
    assert me["username_changed_at"] is None and me["can_rename_after"] is None


def test_can_rename_after_is_30_days_out_then_clears(client):
    session = register(client)
    rename(client, session)
    changed = user_row(client, "bobby").username_changed_at
    me = client.get("/auth/me").json()
    assert me["can_rename_after"][:10] == (changed + timedelta(days=30)).date().isoformat()
    allow_rename_again(client, "bobby")
    assert client.get("/auth/me").json()["can_rename_after"] is None


def test_requires_csrf_and_origin(client):
    session = register(client)
    body = {"username": "bobby", "password": PW}
    assert client.post("/auth/me/username", json=body).status_code == 403
    bad = {**csrf(session), "Origin": "https://evil.example"}
    assert client.post("/auth/me/username", json=body, headers=bad).status_code == 403
    assert user_row(client, "alice") is not None


def test_requires_the_password_step_up(client):
    session = register(client)
    assert rename(client, session, password=None).status_code == 403
    assert rename(client, session, password="wrong-password").status_code == 403
    assert user_row(client, "alice") is not None and events(client) == []


def test_a_fresh_proof_replaces_the_password(client):
    session = register(client)
    grant_fresh(client)
    assert rename(client, session, password=None).status_code == 200


def test_generated_name_accounts_can_rename(google_client):
    session = google_client.post("/auth/google", json={"id_token": "g9|zed@example.com"}).json()
    assert session["username"] == "zed"
    grant_fresh(google_client)
    assert rename(google_client, session, "zed-new", password=None).json()["username"] == "zed-new"


@pytest.mark.parametrize("name", ["ab", "has space", "UPPER@", "x" * 33, ""])
def test_same_policy_as_registration(client, name):
    session = register(client)
    assert rename(client, session, name).status_code == 422


def test_renaming_to_the_current_name_is_refused(client):
    session = register(client)
    assert rename(client, session, "Alice").status_code == 422


def test_taken_name_is_409_with_the_register_message_case_insensitively(client):
    register(client, {"username": "carol", "password": STRONG})
    client.cookies.clear()
    session = register(client)
    response = rename(client, session, "CAROL")
    assert response.status_code == 409 and response.json()["detail"] == "Username already taken"
    client.cookies.clear()
    again = client.post("/auth/register", json={"username": "carol", "password": STRONG})
    assert again.json()["detail"] == response.json()["detail"]


def test_one_rename_per_30_days(client):
    session = register(client)
    fresh = rename(client, session).json()
    again = rename(client, fresh, "third")
    assert again.status_code == 409 and "again after" in again.json()["detail"]
    allow_rename_again(client, "bobby")
    assert rename(client, fresh, "third").status_code == 200


def test_old_name_is_reserved_for_everyone_else_until_it_expires(client):
    session = register(client)
    rename(client, session)
    assert reservations(client)["alice"].user_id == session["id"]
    client.cookies.clear()
    taken = client.post("/auth/register", json={"username": "alice", "password": STRONG})
    assert taken.status_code == 409 and taken.json()["detail"] == "Username already taken"

    expire_reservation(client, "alice")
    assert client.post("/auth/register", json={"username": "alice", "password": STRONG}).status_code == 201


def test_other_account_cannot_rename_into_a_reserved_name(client):
    session = register(client)
    rename(client, session)
    client.cookies.clear()
    other = register(client, {"username": "dave", "password": STRONG})
    response = rename(client, other, "alice", password=STRONG)
    assert response.status_code == 409 and response.json()["detail"] == "Username already taken"


def test_owner_may_switch_back_and_the_reservation_moves(client):
    session = register(client)
    fresh = rename(client, session).json()
    allow_rename_again(client, "bobby")
    assert rename(client, fresh, "alice").status_code == 200
    assert set(reservations(client)) == {"bobby"}  # alice is in use again, bobby is now reserved


def test_unavailable_helper_honours_the_owner(client):
    session = register(client)
    rename(client, session)
    with client.app.state.session_factory() as db:
        assert usernames.unavailable(db, "alice")
        assert not usernames.unavailable(db, "alice", session["id"])


def test_event_is_written_with_the_change(client):
    session = register(client)
    rename(client, session, "bobby")
    (event,) = events(client)
    assert (event.type, event.user_id) == ("user.renamed", session["id"])
    assert json.loads(event.payload) == {"username": "bobby", "old_username": "Alice", "seq": event.id}


def test_failed_rename_leaves_no_event_or_change(client):
    session = register(client)
    rename(client, session, "ab")
    rename(client, session, "Alice")
    assert events(client) == [] and user_row(client, "alice").username_changed_at is None


def test_event_reaches_the_stream(client):
    stream = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    client.app.state.event_relay = EventRelay(client.app.state.session_factory, lambda: stream)
    session = register(client)
    rename(client, session)
    ((_, fields),) = stream.xrange("sn:events:account")
    assert fields["type"] == "user.renamed" and json.loads(fields["payload"])["username"] == "bobby"


def test_other_sessions_are_revoked_and_this_one_survives(client):
    register(client)
    client.post("/auth/login", json=CREDS)  # a second device
    other_token = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    current = client.post("/auth/login", json=CREDS).json()  # the device that renames
    assert rename(client, current).status_code == 200
    assert client.get("/auth/me").status_code == 200
    client.cookies.set(COOKIE_NAME, other_token, path="/")
    assert client.get("/auth/me").status_code == 401
    with client.app.state.session_factory() as db:
        live = [s for s in db.scalars(select(UserSession)) if s.revoked_at is None]
    assert len(live) == 1


def test_revocation_is_published_to_the_other_apps(client, revocations):
    session = register(client)
    rename(client, session)
    assert int(revocations.get(f"sn:minver:{session['id']}")) == 1


def test_throttled_per_user(client):
    session = register(client)
    codes = [rename(client, session, "Alice").status_code for _ in range(12)]
    assert codes[0] == 422 and codes[-1] == 429


def test_notice_mail_names_old_and_new(mail_client):
    session = verified_account(mail_client)
    assert rename(mail_client, session, "bobby").status_code == 200
    mail = last_mail(mail_client, "alice@example.com")
    assert "Alice" in mail.text and "bobby" in mail.text and "30" in mail.text


def test_no_notice_without_a_verified_address(mail_client):
    session = register(mail_client)
    rename(mail_client, session)
    assert sent_to(mail_client, "alice@example.com") == []


def test_rename_event_carries_a_monotonic_seq_equal_to_the_row_id(client):
    session = register(client)
    fresh = rename(client, session).json()
    allow_rename_again(client, "bobby")
    rename(client, fresh, "third")
    first, second = events(client)
    assert json.loads(first.payload)["seq"] == first.id and json.loads(second.payload)["seq"] == second.id
    assert json.loads(first.payload)["username"] == "bobby" and second.id > first.id


def test_a_concurrent_rename_that_passed_the_precheck_loses(client, monkeypatch):
    session = register(client)
    session = rename(client, session, "bobby").json()
    monkeypatch.setattr(usernames, "can_rename_after", lambda user: None)  # as if the stale check had passed
    second = rename(client, session, "other")
    assert second.status_code == 409 and "again" in second.json()["detail"]
    assert user_row(client, "bobby") is not None and len(events(client)) == 1


def test_reservation_check_is_case_insensitive(client):
    session = register(client)
    rename(client, session)
    with client.app.state.session_factory() as db:
        assert usernames.unavailable(db, "ALICE")


@pytest.mark.parametrize("name", ["admin", "root", "no-reply", "center", "werewolf", "jobs", "support"])
def test_system_names_are_refused_everywhere(client, name):
    taken = "Username already taken"
    assert client.post("/auth/register", json={"username": name, "password": STRONG}).json()["detail"] == taken
    assert client.post("/auth/register/combined", data={"username": name, "password": STRONG}).status_code == 409
    session = register(client)
    response = rename(client, session, name)
    assert response.status_code == 409 and response.json()["detail"] == taken


def test_google_handle_avoids_a_system_name(google_client):
    session = google_client.post("/auth/google", json={"id_token": "g8|admin@example.com"}).json()
    assert session["username"] == "admin2"


def test_generated_names_still_work(client):
    from app.routes_methods import _random_handle

    with client.app.state.session_factory() as db:
        assert _random_handle(db).startswith("user-")
