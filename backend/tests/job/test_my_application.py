from tests.job.conftest import ALICE, BOB
from tests.job.test_data import _seed_applicant, _seed_job


def test_the_applicant_changes_their_own_application_until_it_is_reviewed(client):
    job = _seed_job(client, 1)
    row = _seed_applicant(client, job, 2, status="submitted")
    r = client.patch(f"/applications/{row}/mine", json={"cover_letter": "new letter", "contact_email": "bob@example.com"}, headers=BOB)
    assert r.status_code == 200
    assert r.json()["cover_letter"] == "new letter"
    assert r.json()["contact_email"] == "bob@example.com"


def test_someone_else_cannot_change_an_application_and_none_is_shown(client):
    job = _seed_job(client, 1)
    row = _seed_applicant(client, job, 2, status="submitted")
    assert client.patch(f"/applications/{row}/mine", json={"cover_letter": "x"}, headers=ALICE).status_code == 404


def test_an_application_already_reviewed_cannot_be_changed(client):
    job = _seed_job(client, 1)
    row = _seed_applicant(client, job, 2, status="reviewing")
    assert client.patch(f"/applications/{row}/mine", json={"cover_letter": "x"}, headers=BOB).status_code == 409
