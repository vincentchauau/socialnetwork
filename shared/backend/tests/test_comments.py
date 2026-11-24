import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from sn_shared import COOKIE_NAME, comments, create_token, directory
from sn_shared.comments import CommentKind, comments_router
from sn_shared.db import make_engine
from sn_shared.testing import add_person, install_test_keys

install_test_keys()

OWNER = {1: 10}  # thing id -> its owner
BUYERS = {2, 3, 4}  # who bought the product


def visible(db, thing_id, user):
    if thing_id not in OWNER:
        raise HTTPException(404, "Not here")
    return {"id": thing_id, "owner": OWNER[thing_id]}


def must_have_bought(db, thing, user):
    if user.user_id not in BUYERS:
        raise HTTPException(403, "Only buyers can review")


NOTES = CommentKind("note", "/notes/{object_id}/comments", "/note-comments/{comment_id}", visible=visible, content_min=1, content_max=20,
                    moderator=lambda thing, user: thing["owner"] == user.user_id, page_default=2, page_max=3)
REVIEWS = CommentKind("review", "/things/{object_id}/reviews", "/reviews/{comment_id}", visible=visible, rating="required", once=True,
                      may_write=must_have_bought, others_are_hidden=True, newest_first=True, strict_body=True)
ASKS = CommentKind("ask", "/asks/{object_id}/comments", "/ask-comments/{comment_id}", visible=visible, rating="optional")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    install_test_keys(monkeypatch)


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    comments.ensure_table(engine)
    directory.ensure_table_for_sqlite(engine)
    app = FastAPI()
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    for user_id in range(1, 12):  # the people of the tests: the names are read from `users`
        add_person(app.state.session_factory, user_id, {1: "alice", 2: "bob", 3: "carol"}.get(user_id, f"u{user_id - 1}"))
    for kind in (NOTES, REVIEWS, ASKS):
        app.include_router(comments_router(kind))
    with TestClient(app) as test_client:
        yield test_client


def who(user_id, name):
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, name)}"}


ALICE, BOB, CAROL = who(1, "alice"), who(2, "bob"), who(3, "carol")


def test_needs_sign_in_and_a_thing_that_is_there(client):
    assert client.get("/notes/1/comments").status_code == 401
    assert client.get("/notes/9/comments", headers=ALICE).status_code == 404
    assert client.post("/notes/9/comments", json={"content": "x"}, headers=ALICE).status_code == 404


def test_comments_are_added_listed_and_paged_oldest_first(client):
    ids = [client.post("/notes/1/comments", json={"content": f"n{i}"}, headers=BOB).json()["id"] for i in range(5)]
    first = client.get("/notes/1/comments", headers=ALICE).json()
    assert [c["id"] for c in first] == ids[:2]  # the size of a page of this kind
    assert first[0]["username"] == "bob" and first[0]["object_id"] == 1 and first[0]["rating"] is None
    rest = client.get("/notes/1/comments", params={"cursor": ids[1], "limit": 100}, headers=ALICE).json()
    assert [c["id"] for c in rest] == ids[2:5]  # (at most the page_max of 3)


def test_the_words_are_trimmed_and_limited(client):
    assert client.post("/notes/1/comments", json={"content": "  hi  "}, headers=BOB).json()["content"] == "hi"
    for body in ({}, {"content": "  "}, {"content": "x" * 21}, {"content": "ok", "rating": 3}):
        assert client.post("/notes/1/comments", json=body, headers=BOB).status_code == 422, body
    assert client.post("/notes/1/comments", json={"content": "ok", "username": "evil"}, headers=BOB).json()["username"] == "bob"  # ignored
    assert client.post("/things/1/reviews", json={"rating": 4, "username": "evil"}, headers=BOB).status_code == 422  # a strict kind refuses it


def test_a_kind_with_ratings_asks_for_one_and_checks_it(client):
    ask = lambda body: client.post("/asks/1/comments", json=body, headers=BOB)  # noqa: E731
    assert ask({"content": "great", "rating": 5}).json()["rating"] == 5
    assert ask({"content": "no stars"}).json()["rating"] is None  # optional
    for bad in ({"rating": 0}, {"rating": 6}, {"rating": 4.5}, {"rating": "5"}, {"rating": True}):
        assert ask(bad).status_code == 422, bad
    assert client.post("/things/1/reviews", json={"content": "x"}, headers=BOB).status_code == 422  # required


def test_a_review_is_only_for_who_may_write_one_and_only_once(client):
    assert client.post("/things/1/reviews", json={"rating": 4}, headers=ALICE).status_code == 403  # did not buy
    first = client.post("/things/1/reviews", json={"rating": 4, "content": "good"}, headers=BOB)
    assert first.status_code == 201
    assert client.post("/things/1/reviews", json={"rating": 5}, headers=BOB).status_code == 409


def test_what_was_said_is_changed_by_its_author_only(client):
    note = client.post("/notes/1/comments", json={"content": "first"}, headers=BOB).json()
    assert client.patch(f"/note-comments/{note['id']}", json={"content": "second"}, headers=ALICE).status_code == 403
    changed = client.patch(f"/note-comments/{note['id']}", json={"content": " second "}, headers=BOB).json()
    assert changed["content"] == "second" and changed["edited_at"] is not None
    assert client.patch(f"/note-comments/{note['id']}", json={"content": ""}, headers=BOB).status_code == 422
    assert client.patch(f"/note-comments/{note['id']}", json={"rating": 3}, headers=BOB).status_code == 422
    assert client.patch("/note-comments/999", json={"content": "x"}, headers=BOB).status_code == 404
    assert client.patch(f"/reviews/{note['id']}", json={"content": "x"}, headers=BOB).status_code == 404  # another kind of thing


def test_somebody_elses_review_looks_like_none_and_a_rating_can_be_mended(client):
    review = client.post("/things/1/reviews", json={"rating": 4}, headers=BOB).json()
    assert client.patch(f"/reviews/{review['id']}", json={"rating": 1}, headers=ALICE).status_code == 404
    assert client.delete(f"/reviews/{review['id']}", headers=ALICE).status_code == 404
    assert client.patch(f"/reviews/{review['id']}", json={"rating": 2}, headers=BOB).json()["rating"] == 2
    assert client.patch(f"/reviews/{review['id']}", json={"rating": None}, headers=BOB).status_code == 422  # required


def test_the_owner_of_the_thing_may_delete_what_others_said_and_nobody_else(client):
    note = client.post("/notes/1/comments", json={"content": "hi"}, headers=BOB).json()
    assert client.delete(f"/note-comments/{note['id']}", headers=CAROL).status_code == 403
    assert client.delete(f"/note-comments/{note['id']}", headers=who(10, "owner")).status_code == 204
    again = client.post("/notes/1/comments", json={"content": "hi"}, headers=BOB).json()
    assert client.delete(f"/note-comments/{again['id']}", headers=BOB).status_code == 204  # the author
    assert client.delete(f"/note-comments/{again['id']}", headers=BOB).status_code == 404


def test_newest_first_and_the_cursor_goes_backwards(client):
    ids = [client.post("/things/1/reviews", json={"rating": number}, headers=who(number + 1, f"u{number}")).json()["id"] for number in (1, 2, 3)]
    assert [r["id"] for r in client.get("/things/1/reviews", headers=ALICE).json()] == ids[::-1]
    older = client.get("/things/1/reviews", params={"cursor": ids[2], "limit": 1}, headers=ALICE).json()
    assert [r["id"] for r in older] == [ids[1]]


def test_the_counts_and_the_ratings_of_a_set_of_things(client):
    client.post("/things/1/reviews", json={"rating": 4}, headers=BOB)
    client.post("/asks/1/comments", json={"content": "q", "rating": 2}, headers=ALICE)
    client.post("/asks/1/comments", json={"content": "q2"}, headers=ALICE)
    with client.app.state.session_factory() as db:
        assert comments.counts(db, "ask", [1, 2]) == {1: 2} and comments.counts(db, "ask", []) == {}
        assert comments.rating_stats(db, "ask", [1]) == {1: (2.0, 1)} and comments.rating_stats(db, "review", [1, 5]) == {1: (4.0, 1)}


def test_what_happens_to_comments_when_a_thing_or_an_account_goes(client):
    client.post("/notes/1/comments", json={"content": "a"}, headers=BOB)
    client.post("/things/1/reviews", json={"rating": 5}, headers=BOB)
    with client.app.state.session_factory() as db:
        add_person(client.app.state.session_factory, 2, "robert")  # a rename is only a change of the `users` row
        assert {c.username for c in directory.attach_names(db, db.query(comments.Comment))} == {"robert"}
        assert client.get("/notes/1/comments", headers=ALICE).json()[0]["username"] == "robert"
        comments.anonymize_user(db, 2, ["review"])
        comments.forget_user(db, 2, ["note"])
        db.commit()
        left = directory.attach_names(db, db.query(comments.Comment))
        assert [(c.object_type, c.user_id, c.username) for c in left] == [("review", -2, directory.DELETED_USERNAME)]
        comments.forget_object(db, "review", 1)
        db.commit()
        assert db.query(comments.Comment).count() == 0
