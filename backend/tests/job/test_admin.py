from sqlalchemy import func, select

from api.job.models import JobApplicant
from sn_shared import COOKIE_NAME, create_token
from tests.job.conftest import ALICE

ADMIN = {"Cookie": f"{COOKIE_NAME}={create_token(9, 'root', group='admin')}"}

JOB = {"owner_id": 1, "title": "Dev", "company": "Acme", "employment_type": "full_time"}


def _count(client, model) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_admin_requires_admin_role(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/tables", headers=ALICE).status_code == 200
    assert client.delete("/records/job_descriptions/1").status_code == 401
    assert client.delete("/records/job_descriptions/1", headers=ALICE).status_code == 404


def test_admin_lists_the_job_tables(client):
    names = {t["name"] for t in client.get("/records/tables", headers=ADMIN).json()}
    assert names == {"job_descriptions", "job_applications"}


def test_admin_crud_job_description(client):
    r = client.post("/records/job_descriptions", json={"values": JOB}, headers=ADMIN)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    assert client.get("/records/job_descriptions", headers=ADMIN).json()["total"] == 1
    r = client.patch(f"/records/job_descriptions/{job_id}", json={"values": {"title": "Lead"}}, headers=ADMIN)
    assert r.json()["title"] == "Lead"
    assert client.delete(f"/records/job_descriptions/{job_id}", headers=ADMIN).status_code == 204
    assert client.delete(f"/records/job_descriptions/{job_id}", headers=ADMIN).status_code == 404


def test_deleting_a_job_removes_its_applicants(client):
    job_id = client.post("/records/job_descriptions", json={"values": JOB}, headers=ADMIN).json()["id"]
    other_id = client.post("/records/job_descriptions", json={"values": JOB}, headers=ADMIN).json()["id"]
    with client.app.state.session_factory() as db:
        db.add_all([JobApplicant(job_description_id=job_id, user_id=2), JobApplicant(job_description_id=other_id, user_id=2)])
        db.commit()
    assert client.delete(f"/records/job_descriptions/{job_id}", headers=ADMIN).status_code == 204
    with client.app.state.session_factory() as db:
        assert [a.job_description_id for a in db.scalars(select(JobApplicant))] == [other_id]


def test_admin_crud_job_applicant(client):
    job_id = client.post("/records/job_descriptions", json={"values": JOB}, headers=ADMIN).json()["id"]
    r = client.post("/records/job_applications", json={"values": {"job_description_id": job_id, "user_id": 2}}, headers=ADMIN)
    assert r.status_code == 201, r.text
    row_id = r.json()["id"]
    r = client.patch(f"/records/job_applications/{row_id}", json={"values": {"employer_note": "ok"}}, headers=ADMIN)
    assert r.json()["employer_note"] == "ok"
    assert client.delete(f"/records/job_applications/{row_id}", headers=ADMIN).status_code == 204
    assert _count(client, JobApplicant) == 0


def test_admin_job_applicant_rows_carry_job_title_and_username_labels(client):
    from sn_shared.testing import add_person

    add_person(client.app.state.session_factory, 2, "bob")
    job_id = client.post("/records/job_descriptions", json={"values": JOB}, headers=ADMIN).json()["id"]
    client.post("/records/job_applications", json={"values": {"job_description_id": job_id, "user_id": 2}}, headers=ADMIN)
    cols = {c["name"]: c for c in next(t for t in client.get("/records/tables", headers=ADMIN).json() if t["name"] == "job_applications")["columns"]}
    assert cols["job_description_id"]["ref"] == {"table": "job_descriptions", "label": "title", "key": "id"}
    assert cols["user_id"]["ref"] == {"table": "users", "label": "username", "key": "id"}
    body = client.get("/records/job_applications", headers=ADMIN).json()
    assert body["labels"] == {"job_description_id": {str(job_id): "Dev"}, "user_id": {"2": "bob"}}
