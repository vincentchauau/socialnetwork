"""The social side: people, friends, blocks, reports, notifications, and what happens when an account goes or changes."""

from sn_shared import COOKIE_NAME, create_token
from sn_shared.directory import DELETED_USERNAME
from sn_shared.testing import add_person

from tests.chat.conftest import ALLOWED_ORIGIN
from tests.chat.social.people import join, make_people


def call(client, method, path, uid=1, name="alice", **kwargs):
    """A call as `name`, whose token is minted here and not through the chat helpers: those add the person to `users`, and some tests need one who is not there."""
    headers = {"Cookie": f"{COOKIE_NAME}={create_token(uid, name)}", "Origin": ALLOWED_ORIGIN}
    return client.request(method, path, headers=headers, **kwargs)


def as_admin(client, method, path, uid=99, name="root", **kwargs):
    headers = {"Cookie": f"{COOKIE_NAME}={create_token(uid, name, group='admin')}", "Origin": ALLOWED_ORIGIN}
    return client.request(method, path, headers=headers, **kwargs)


# ---- people and profiles -----------------------------------------------------------------------------------------


def test_somebody_who_is_not_in_users_is_not_a_person(raw_client):
    assert call(raw_client, "GET", "/me", 7, "ghost").status_code == 404
    assert call(raw_client, "GET", "/people/ghost", 1, "alice").status_code == 404


def test_the_summary_is_for_friends_unless_its_owner_made_it_public(raw_client):
    make_people(raw_client)
    join(raw_client, 1, "alice", headline="Gardener", summary="I grow roses")
    stranger = call(raw_client, "GET", "/people/alice", 2, "bob").json()
    assert stranger["headline"] == "Gardener" and stranger["summary"] is None  # a stranger reads the headline, not the summary
    call(raw_client, "POST", "/friends/2", 1, "alice")
    call(raw_client, "POST", "/friends/1/accept", 2, "bob")
    assert call(raw_client, "GET", "/people/alice", 2, "bob").json()["summary"] == "I grow roses"
    assert call(raw_client, "GET", "/people/alice", 3, "carol").json()["summary"] is None  # still not carol
    join(raw_client, 1, "alice", headline="Gardener", summary="I grow roses", summary_public=True)
    assert call(raw_client, "GET", "/people/alice", 3, "carol").json()["summary"] == "I grow roses"


# ---- friends -----------------------------------------------------------------------------------------------------


def test_asking_the_one_who_asked_you_is_the_yes(raw_client):
    make_people(raw_client)
    call(raw_client, "POST", "/friends/2", 1, "alice")
    crossed = call(raw_client, "POST", "/friends/1", 2, "bob")
    assert crossed.json()["relation"] == "friends"


def test_a_person_cannot_befriend_themselves_or_someone_who_does_not_exist(raw_client):
    make_people(raw_client)
    assert call(raw_client, "POST", "/friends/1", 1, "alice").status_code == 422
    assert call(raw_client, "POST", "/friends/77", 1, "alice").status_code == 404


def test_friend_requests_are_limited_per_day(raw_client, monkeypatch):
    from api.chat.social import service

    monkeypatch.setattr(service, "MAX_REQUESTS_PER_DAY", 2)
    make_people(raw_client)
    join(raw_client, 4, "dave")
    assert call(raw_client, "POST", "/friends/2", 1, "alice").status_code == 200
    assert call(raw_client, "POST", "/friends/3", 1, "alice").status_code == 200
    assert call(raw_client, "POST", "/friends/4", 1, "alice").status_code == 429


# ---- blocks ------------------------------------------------------------------------------------------------------


# ---- reports -----------------------------------------------------------------------------------------------------


def test_a_report_is_kept_once_while_open_and_reviewed_by_an_administrator(raw_client):
    make_people(raw_client)
    body = {"target_type": "user", "target_id": "2", "reason": "spam", "details": "  sends links "}
    first = call(raw_client, "POST", "/reports", 1, "alice", json=body)
    assert first.status_code == 201 and first.json()["details"] == "sends links" and first.json()["status"] == "open"
    again = call(raw_client, "POST", "/reports", 1, "alice", json=body)
    assert again.json()["id"] == first.json()["id"]  # the same report, not another
    assert call(raw_client, "POST", "/reports", 1, "alice", json={**body, "reason": "rude"}).status_code == 422
    assert call(raw_client, "GET", "/reports", 1, "alice").status_code == 403  # a person does not read the reports
    listed = as_admin(raw_client, "GET", "/reports").json()
    assert [(r["reporter_id"], r["target_id"]) for r in listed] == [(1, "2")]
    handled = as_admin(raw_client, "PATCH", f"/reports/{first.json()['id']}", json={"status": "actioned"}).json()
    assert handled["status"] == "actioned" and "handled_by" not in handled
    assert as_admin(raw_client, "GET", "/reports").json() == []
    assert call(raw_client, "PATCH", f"/reports/{first.json()['id']}", 1, "alice", json={"status": "reviewed"}).status_code == 403
    assert as_admin(raw_client, "PATCH", "/reports/999", json={"status": "reviewed"}).status_code == 404


def test_a_person_takes_back_their_own_report_while_it_is_open_and_never_another_ones(raw_client):
    make_people(raw_client)
    body = {"target_type": "user", "target_id": "2", "reason": "spam", "details": ""}
    report_id = call(raw_client, "POST", "/reports", 1, "alice", json=body).json()["id"]
    assert [r["id"] for r in call(raw_client, "GET", "/reports/mine", 1, "alice").json()] == [report_id]
    assert call(raw_client, "GET", "/reports/mine", 2, "bob").json() == []  # nobody reads the reports of another
    assert call(raw_client, "DELETE", f"/reports/{report_id}", 2, "bob").status_code == 404
    assert call(raw_client, "DELETE", f"/reports/{report_id}", 1, "alice").status_code == 204
    assert call(raw_client, "GET", "/reports/mine", 1, "alice").json() == [] and as_admin(raw_client, "GET", "/reports").json() == []
    assert call(raw_client, "DELETE", f"/reports/{report_id}", 1, "alice").status_code == 404
    again = call(raw_client, "POST", "/reports", 1, "alice", json=body).json()["id"]
    as_admin(raw_client, "PATCH", f"/reports/{again}", json={"status": "reviewed"})
    assert call(raw_client, "DELETE", f"/reports/{again}", 1, "alice").status_code == 409  # one that was looked at stays as it was


def as_role(client, group, method, path, uid=98, name="mod", **kwargs):
    headers = {"Cookie": f"{COOKIE_NAME}={create_token(uid, name, group=group)}", "Origin": ALLOWED_ORIGIN}
    return client.request(method, path, headers=headers, **kwargs)


def test_moderators_work_the_reports_queue_and_nothing_else_of_the_admin(raw_client):
    make_people(raw_client)
    body = {"target_type": "user", "target_id": "2", "reason": "spam"}
    report_id = call(raw_client, "POST", "/reports", 1, "alice", json=body).json()["id"]
    assert raw_client.get("/reports").status_code == 401
    assert [r["id"] for r in as_role(raw_client, "moderator", "GET", "/reports").json()] == [report_id]
    handled = as_role(raw_client, "moderator", "PATCH", f"/reports/{report_id}", json={"status": "reviewed"})
    assert handled.status_code == 200 and handled.json()["status"] == "reviewed"
    assert as_role(raw_client, "moderator", "PATCH", "/reports/999", json={"status": "reviewed"}).status_code == 404
    assert as_role(raw_client, "user", "GET", "/reports").status_code == 403
    assert as_role(raw_client, "user", "PATCH", f"/reports/{report_id}", json={"status": "reviewed"}).status_code == 403
    assert as_role(raw_client, "moderator", "GET", "/records/tables").status_code == 200  # a moderator reads the tables (CRU)


def test_reports_are_limited_per_hour(raw_client, monkeypatch):
    from api.chat.social import service

    monkeypatch.setattr(service, "MAX_REPORTS_PER_HOUR", 2)
    make_people(raw_client)
    for n in range(2):
        assert call(raw_client, "POST", "/reports", 1, "alice", json={"target_type": "message", "target_id": str(n), "reason": "abuse"}).status_code == 201
    assert call(raw_client, "POST", "/reports", 1, "alice", json={"target_type": "message", "target_id": "9", "reason": "abuse"}).status_code == 429


# ---- accounts that go or change ----------------------------------------------------------------------------------


def test_a_deleted_account_leaves_nothing_of_the_social_side_except_what_others_reported(raw_client):
    from api.chat.models import Message  # noqa: F401  (the chat's own tables stay as they were)
    from api.chat.social.events import on_user_deleted, on_user_renamed
    from api.chat.social.models import Edge, Notification, Report

    make_people(raw_client)
    call(raw_client, "POST", "/friends/2", 1, "alice")
    call(raw_client, "POST", "/friends/1/accept", 2, "bob")
    call(raw_client, "POST", "/friends/3", 2, "bob")
    call(raw_client, "POST", "/blocks/1", 3, "carol")
    call(raw_client, "POST", "/reports", 1, "alice", json={"target_type": "user", "target_id": "3", "reason": "spam"})
    with raw_client.app.state.session_factory() as db:
        on_user_renamed(db, 1, "alicia")  # nothing to do: a notice keeps the id, the name is read from `users`
        db.commit()
        assert all("username" not in n.payload for n in db.query(Notification).filter(Notification.actor_id == 1))
        for _ in range(2):  # at least once: twice is the same
            on_user_deleted(db, 1)
            db.commit()
        assert [(e.src_id, e.dst_id, e.kind) for e in db.query(Edge)] == [(2, 3, "friend")]  # only bob's request to carol is left; the block is gone
        assert db.query(Notification).filter(Notification.actor_id == 1).count() == 0
        assert [r.reporter_id for r in db.query(Report)] == [0]  # the report stays, the reporter is gone
