import pytest

from tests.conftest import ALICE, BOB, CAROL, post_job

APPLICATION = {
    "cover_letter": "Hire me",
    "resume_text": "10 years of things",
    "contact_email": "bob@example.com",
}


def apply(client, job_id, headers=BOB, body=None):
    return client.post(f"/jobs/{job_id}/apply", json=APPLICATION if body is None else body,
                       headers=headers)


def test_apply_happy_path(client):
    job = post_job(client)

    response = apply(client, job["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert body["job_title"] == "Backend Engineer"
    assert body["contact_email"] == "bob@example.com"
    assert "employer_note" not in body and "note" not in body
    assert "applicant_id" not in body


def test_apply_requires_auth(client):
    job = post_job(client)
    assert client.post(f"/jobs/{job['id']}/apply", json={}).status_code == 401


def test_apply_to_missing_job(client):
    assert apply(client, 404).status_code == 404


def test_cannot_apply_twice(client):
    job = post_job(client)
    apply(client, job["id"])
    assert apply(client, job["id"]).status_code == 409


def test_cannot_apply_to_own_posting(client):
    job = post_job(client)
    assert apply(client, job["id"], headers=ALICE).status_code == 403


def test_cannot_apply_to_closed_posting(client):
    job = post_job(client)
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)
    assert apply(client, job["id"]).status_code == 404  # closed jobs are invisible to others


def test_cannot_apply_to_expired_posting(client):
    from datetime import datetime, timedelta, timezone

    from app.models import Posting

    job = post_job(client)
    with client.app.state.session_factory() as session:
        session.get(Posting, job["id"]).expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()
    assert apply(client, job["id"]).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"cover_letter": "x" * 5001},
        {"resume_text": "x" * 20001},
        {"contact_email": "not-an-email"},
        {"contact_email": "a@b"},
        {"contact_email": "a b@example.com"},
        {"contact_email": "a@example.com\nBcc: x@y.z"},
        {"contact_email": "x" * 250 + "@example.com"},
    ],
)
def test_apply_validation(client, body):
    job = post_job(client)
    assert apply(client, job["id"], body=body).status_code == 422


def test_apply_with_empty_body_is_allowed(client):
    job = post_job(client)
    response = apply(client, job["id"], body={})
    assert response.status_code == 201
    assert response.json()["contact_email"] is None


def test_my_applications_only_shows_own(client):
    job = post_job(client)
    apply(client, job["id"], headers=BOB)
    apply(client, job["id"], headers=CAROL)

    mine = client.get("/me/applications", headers=BOB).json()

    assert len(mine) == 1
    assert mine[0]["company"] == "Acme"
    assert client.get("/me/applications").status_code == 401


def test_employer_lists_applicants_only_for_own_posting(client):
    job = post_job(client)
    apply(client, job["id"], headers=BOB)

    response = client.get(f"/jobs/{job['id']}/applications", headers=ALICE)

    assert response.status_code == 200
    assert response.json()[0]["applicant_username"] == "bob"
    assert client.get(f"/jobs/{job['id']}/applications", headers=CAROL).status_code == 403
    assert client.get(f"/jobs/{job['id']}/applications", headers=BOB).status_code == 403
    assert client.get(f"/jobs/{job['id']}/applications").status_code == 401
    assert client.get("/jobs/999/applications", headers=ALICE).status_code == 404


def test_employer_updates_status_and_note_applicant_never_sees_note(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()

    response = client.patch(
        f"/applications/{application['id']}",
        json={"status": "shortlisted", "note": "strong candidate"},
        headers=ALICE,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "shortlisted"
    assert response.json()["note"] == "strong candidate"
    mine = client.get("/me/applications", headers=BOB).json()[0]
    assert mine["status"] == "shortlisted"
    assert "strong candidate" not in str(mine)
    listed = client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json()[0]
    assert listed["note"] == "strong candidate"


def test_patch_without_note_keeps_existing_note(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    client.patch(f"/applications/{application['id']}",
                 json={"status": "reviewing", "note": "n1"}, headers=ALICE)
    response = client.patch(f"/applications/{application['id']}",
                            json={"status": "rejected"}, headers=ALICE)
    assert response.json()["note"] == "n1"


@pytest.mark.parametrize(
    "payload", [{"status": "maybe"}, {}, {"status": "hired", "note": "x" * 2001}]
)
def test_patch_validation(client, payload):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    response = client.patch(f"/applications/{application['id']}", json=payload, headers=ALICE)
    assert response.status_code == 422


def test_only_the_employer_may_change_status(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    url = f"/applications/{application['id']}"
    assert client.patch(url, json={"status": "hired"}, headers=BOB).status_code == 403
    assert client.patch(url, json={"status": "hired"}, headers=CAROL).status_code == 403
    assert client.patch(url, json={"status": "hired"}).status_code == 401
    assert client.patch("/applications/999", json={"status": "hired"}, headers=ALICE).status_code == 404


def test_employer_can_review_applications_of_closed_posting(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)
    response = client.patch(f"/applications/{application['id']}",
                            json={"status": "rejected"}, headers=ALICE)
    assert response.status_code == 200


def test_applicant_can_withdraw_until_hired(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    url = f"/applications/{application['id']}"

    assert client.delete(url, headers=CAROL).status_code == 404
    assert client.delete(url).status_code == 401
    assert client.delete(url, headers=BOB).status_code == 204
    assert client.get("/me/applications", headers=BOB).json() == []
    assert apply(client, job["id"]).status_code == 201  # may re-apply after withdrawing


def test_cannot_withdraw_once_hired(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    client.patch(f"/applications/{application['id']}", json={"status": "hired"}, headers=ALICE)
    assert client.delete(f"/applications/{application['id']}", headers=BOB).status_code == 409


def test_employer_cannot_withdraw_on_behalf(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    assert client.delete(f"/applications/{application['id']}", headers=ALICE).status_code == 404


def test_profile_visible_to_employer_only_for_applicants(client):
    client.put("/me/profile", json={"headline": "Dev", "skills": ["py"], "about": "hi",
                                    "open_to_work": True}, headers=BOB)
    job = post_job(client)
    other_job = post_job(client, headers=CAROL)
    apply(client, job["id"], headers=BOB)

    listed = client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json()[0]
    assert listed["profile"]["headline"] == "Dev"
    assert client.get(f"/jobs/{other_job['id']}/applications", headers=CAROL).json() == []
