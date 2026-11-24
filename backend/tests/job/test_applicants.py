import pytest

from tests.job.conftest import ALICE, BOB, CAROL, post_job

APPLICATION = {
    "cover_letter": "Hire me",
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

    from api.job.models import JobDescription

    job = post_job(client)
    with client.app.state.session_factory() as session:
        session.get(JobDescription, job["id"]).expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()
    assert apply(client, job["id"]).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"cover_letter": "x" * 5001},
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
    assert client.get(f"/jobs/{job['id']}/applications", headers=CAROL).status_code == 404
    assert client.get(f"/jobs/{job['id']}/applications", headers=BOB).status_code == 404
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
    assert client.patch(url, json={"status": "reviewing"}, headers=BOB).status_code == 404
    assert client.patch(url, json={"status": "reviewing"}, headers=CAROL).status_code == 404
    assert client.patch(url, json={"status": "reviewing"}).status_code == 401
    assert client.patch("/applications/999", json={"status": "hired"}, headers=ALICE).status_code == 404


@pytest.mark.parametrize(
    "path,target",
    [
        (["reviewing"], "submitted"),
        (["rejected"], "reviewing"),
        (["rejected"], "hired"),
        (["reviewing", "hired"], "rejected"),
        (["reviewing", "hired"], "shortlisted"),
        ([], "hired"),
        (["shortlisted"], "submitted"),
        (["shortlisted"], "reviewing"),
        (["reviewing", "hired"], "submitted"),
    ],
)
def test_invalid_status_transition_is_409(client, path, target):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    url = f"/applications/{application['id']}"
    for step in path:
        assert client.patch(url, json={"status": step}, headers=ALICE).status_code == 200
    response = client.patch(url, json={"status": target}, headers=ALICE)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "path",
    [
        ["reviewing", "shortlisted", "hired"],
        ["shortlisted", "rejected"],
        ["rejected"],
        ["reviewing", "hired"],
    ],
)
def test_valid_status_transitions(client, path):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    url = f"/applications/{application['id']}"
    for step in path:
        assert client.patch(url, json={"status": step}, headers=ALICE).status_code == 200


def test_same_status_allows_note_only_update(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    url = f"/applications/{application['id']}"
    client.patch(url, json={"status": "reviewing"}, headers=ALICE)
    client.patch(url, json={"status": "hired"}, headers=ALICE)
    response = client.patch(url, json={"status": "hired", "note": "start monday"}, headers=ALICE)
    assert response.status_code == 200
    assert response.json()["note"] == "start monday"


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
    url = f"/applications/{application['id']}"
    client.patch(url, json={"status": "reviewing"}, headers=ALICE)
    client.patch(url, json={"status": "hired"}, headers=ALICE)
    assert client.delete(f"/applications/{application['id']}", headers=BOB).status_code == 409


def test_employer_cannot_withdraw_on_behalf(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    assert client.delete(f"/applications/{application['id']}", headers=ALICE).status_code == 404


RESUME = {
    "headline": "Dev",
    "summary": "hi",
    "skills": [{"name": "Python", "level": "advanced", "years": 5}],
    "experience": [{"company": "Acme", "title": "Engineer", "start": "2020-01", "end": None, "description": "built"}],
    "education": [{"school": "HUST", "degree": "BSc", "field": "CS", "start": "2015-09", "end": "2019-06"}],
    "languages": [{"language": "English", "proficiency": "fluent"}],
}


def test_the_resume_sent_with_an_application_is_kept_as_it_was_and_seen_by_the_employer(client):
    job = post_job(client)
    other_job = post_job(client, headers=CAROL)
    application = apply(client, job["id"], headers=BOB, body={"resume": RESUME}).json()
    assert application["resume"]["skills"][0] == {"name": "Python", "level": "advanced", "years": 5}
    listed = client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json()[0]
    assert listed["resume"]["experience"][0]["company"] == "Acme" and listed["resume"]["headline"] == "Dev"
    assert client.get(f"/jobs/{other_job['id']}/applications", headers=CAROL).json() == []


def test_an_application_without_a_resume_has_none(client):
    job = post_job(client)
    assert apply(client, job["id"]).json()["resume"] is None


def test_a_resume_over_the_limits_is_refused(client):
    job = post_job(client)
    too_many = {"skills": [{"name": f"s{i}"} for i in range(51)]}
    assert apply(client, job["id"], body={"resume": too_many}).status_code == 422
    assert apply(client, job["id"], body={"resume": {"skills": [{"name": "x", "level": "godlike"}]}}).status_code == 422


def test_every_step_of_an_application_is_recorded_with_who_made_it(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    assert [(s["status"], s["by"]) for s in application["history"]] == [("submitted", "applicant")]
    for step in ("reviewing", "interview", "offer", "hired"):
        client.patch(f"/applications/{application['id']}", json={"status": step}, headers=ALICE)
    mine = client.get("/me/applications", headers=BOB).json()[0]
    assert [(s["status"], s["by"]) for s in mine["history"]] == [
        ("submitted", "applicant"), ("reviewing", "employer"), ("interview", "employer"), ("offer", "employer"), ("hired", "employer"),
    ]
    assert mine["status"] == "hired"
    listed = client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json()[0]
    assert len(listed["history"]) == 5


def test_a_step_that_changes_nothing_is_not_recorded_again(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    client.patch(f"/applications/{application['id']}", json={"status": "reviewing", "note": "a"}, headers=ALICE)
    client.patch(f"/applications/{application['id']}", json={"status": "reviewing", "note": "b"}, headers=ALICE)
    assert len(client.get("/me/applications", headers=BOB).json()[0]["history"]) == 2


def test_the_steps_that_cannot_be_skipped_or_undone(client):
    job = post_job(client)
    application = apply(client, job["id"]).json()
    url = f"/applications/{application['id']}"
    assert client.patch(url, json={"status": "offer"}, headers=ALICE).status_code == 409  # not from submitted
    assert client.patch(url, json={"status": "hired"}, headers=ALICE).status_code == 409
    client.patch(url, json={"status": "rejected"}, headers=ALICE)
    assert client.patch(url, json={"status": "reviewing"}, headers=ALICE).status_code == 409  # rejected is final
