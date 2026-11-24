import pytest

from tests.job.conftest import ALICE, BOB, CAROL, post_job


def test_save_and_unsave_are_idempotent(client):
    job = post_job(client)
    url = f"/jobs/{job['id']}/save"

    assert client.put(url, headers=BOB).status_code == 204
    assert client.put(url, headers=BOB).status_code == 204
    saved = client.get("/me/saved", headers=BOB).json()
    assert [item["id"] for item in saved] == [job["id"]]
    assert saved[0]["saved"] is True

    assert client.delete(url, headers=BOB).status_code == 204
    assert client.delete(url, headers=BOB).status_code == 204
    assert client.get("/me/saved", headers=BOB).json() == []


def test_save_requires_auth_and_existing_visible_job(client):
    job = post_job(client)
    assert client.put(f"/jobs/{job['id']}/save").status_code == 401
    assert client.get("/me/saved").status_code == 401
    assert client.put("/jobs/999/save", headers=BOB).status_code == 404
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)
    assert client.put(f"/jobs/{job['id']}/save", headers=BOB).status_code == 404


def test_saved_lists_are_per_user_and_hide_closed_jobs(client):
    job = post_job(client)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)
    assert client.get("/me/saved", headers=ALICE).json() == []
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)
    assert client.get("/me/saved", headers=BOB).json() == []


def apply(client, job_id, headers=BOB, **body):
    return client.post(f"/jobs/{job_id}/apply", json=body, headers=headers)


def test_saving_does_not_count_as_applying(client):
    job = post_job(client)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)
    seen = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert seen["saved"] is True and seen["applied"] is False
    assert client.get(f"/jobs/{job['id']}", headers=ALICE).json()["application_count"] == 0
    assert client.get("/me/applications", headers=BOB).json() == []
    assert client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json() == []


def test_a_saved_job_can_be_applied_to_and_stays_saved(client):
    job = post_job(client)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)
    assert apply(client, job["id"], cover_letter="hi").status_code == 201
    seen = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert seen["saved"] is True and seen["applied"] is True
    assert client.get(f"/jobs/{job['id']}", headers=ALICE).json()["application_count"] == 1


def test_unsaving_an_applied_job_keeps_the_application(client):
    job = post_job(client)
    apply(client, job["id"])
    client.put(f"/jobs/{job['id']}/save", headers=BOB)
    client.delete(f"/jobs/{job['id']}/save", headers=BOB)
    seen = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert seen["saved"] is False and seen["applied"] is True
    assert len(client.get("/me/applications", headers=BOB).json()) == 1


def test_withdrawing_keeps_the_job_saved(client):
    job = post_job(client)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)
    application = apply(client, job["id"]).json()
    assert client.delete(f"/applications/{application['id']}", headers=BOB).status_code == 204
    seen = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert seen["saved"] is True and seen["applied"] is False
    assert client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json() == []
    assert apply(client, job["id"]).status_code == 201  # and it can be applied to again


def test_deleting_a_job_removes_who_saved_and_applied(client):
    job = post_job(client)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)
    apply(client, job["id"], headers=CAROL)
    assert client.delete(f"/jobs/{job['id']}", headers=ALICE).status_code == 204
    assert client.get("/me/saved", headers=BOB).json() == []
    assert client.get("/me/applications", headers=CAROL).json() == []
