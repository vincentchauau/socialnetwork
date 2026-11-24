"""The comments on a job (`sn_shared.comments`): questions beside the description."""

from tests.job.conftest import ALICE, BOB, CAROL, post_job


def ask(client, job_id, headers=BOB, **body):
    return client.post(f"/jobs/{job_id}/comments", json=body, headers=headers)


def test_anybody_who_sees_a_job_comments_on_it(client):
    job = post_job(client)
    assert ask(client, job["id"], content="Is it remote?").status_code == 201
    assert ask(client, job["id"], headers=ALICE, content="Two days a week").json()["username"] == "alice"
    listed = client.get(f"/jobs/{job['id']}/comments", headers=CAROL).json()
    assert [(c["username"], c["rating"]) for c in listed] == [("bob", None), ("alice", None)]


def test_a_job_comment_has_words_and_no_stars(client):
    job = post_job(client)
    for body in ({}, {"content": "  "}, {"content": "x" * 1001}, {"content": "hi", "rating": 4}):
        assert ask(client, job["id"], **body).status_code == 422, body


def test_a_job_that_others_cannot_see_has_no_comments_for_them(client):
    job = post_job(client, status="draft")
    assert ask(client, job["id"]).status_code == 404
    assert client.get(f"/jobs/{job['id']}/comments", headers=BOB).status_code == 404
    assert ask(client, job["id"], headers=ALICE, content="to do").status_code == 201
    client.patch(f"/jobs/{job['id']}", json={"status": "open"}, headers=ALICE)
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)
    assert ask(client, job["id"]).status_code == 404


def test_the_author_changes_theirs_and_the_owner_of_the_job_deletes_any(client):
    job = post_job(client)
    said = ask(client, job["id"], content="first").json()
    assert client.patch(f"/comments/{said['id']}", json={"content": "second"}, headers=CAROL).status_code == 403
    assert client.patch(f"/comments/{said['id']}", json={"content": "second"}, headers=BOB).json()["content"] == "second"
    assert client.delete(f"/comments/{said['id']}", headers=CAROL).status_code == 403
    assert client.delete(f"/comments/{said['id']}", headers=ALICE).status_code == 204


def test_deleting_the_job_takes_its_comments_and_tags_with_it(client):
    job = post_job(client)
    ask(client, job["id"], content="hi")
    assert client.delete(f"/jobs/{job['id']}", headers=ALICE).status_code == 204
    from sn_shared.comments import Comment

    with client.app.state.session_factory() as db:
        assert db.query(Comment).count() == 0
