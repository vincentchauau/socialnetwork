from sqlalchemy import func, select

from api.job.models import JobApplicant, JobDescription
from tests.job.conftest import ALICE, BOB, CAROL

JOB = {"title": "Dev", "company": "Acme", "employment_type": "full_time"}


def _seed_job(client, owner_id: int) -> int:
    with client.app.state.session_factory() as db:
        job = JobDescription(owner_id=owner_id, **JOB)
        db.add(job)
        db.commit()
        return job.id


def _seed_applicant(client, job_id: int, user_id: int, status: str | None = "applied") -> int:
    with client.app.state.session_factory() as db:
        row = JobApplicant(job_description_id=job_id, user_id=user_id, status=status, employer_note="secret")
        db.add(row)
        db.commit()
        return row.id


def _count(client, model) -> int:
    with client.app.state.session_factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_data_requires_login(client):
    assert client.get("/records/tables").status_code == 401
    assert client.get("/records/job_descriptions").status_code == 401
    assert client.delete("/records/job_descriptions/1").status_code == 401


def test_tables_and_ops(client):
    tables = {t["name"]: t["writable"] for t in client.get("/records/tables", headers=ALICE).json()}
    assert tables["job_descriptions"] is True and tables["job_applications"] is True


def test_jobs_are_isolated_and_owner_is_forced(client):
    mine, theirs = _seed_job(client, 1), _seed_job(client, 2)
    rows = client.get("/records/job_descriptions", headers=ALICE).json()["rows"]
    assert [r["id"] for r in rows] == [mine]
    assert client.get(f"/records/job_descriptions/{theirs}", headers=ALICE).status_code == 404
    assert client.patch(f"/records/job_descriptions/{theirs}", json={"values": {"title": "x"}}, headers=ALICE).status_code == 404
    r = client.post("/records/job_descriptions", json={"values": JOB}, headers=ALICE)
    assert r.status_code == 201 and r.json()["owner_id"] == 1
    r = client.post("/records/job_descriptions", json={"values": {**JOB, "owner_id": 2}}, headers=ALICE)
    assert r.status_code == 422


def test_deleting_a_job_runs_the_cleanup(client):
    job = _seed_job(client, 1)
    _seed_applicant(client, job, 2)
    other = _seed_job(client, 2)
    assert client.delete(f"/records/job_descriptions/{other}", headers=ALICE).status_code == 404
    assert client.delete(f"/records/job_descriptions/{job}", headers=ALICE).status_code == 204
    assert _count(client, JobApplicant) == 0
    assert _count(client, JobDescription) == 1


def test_applicants_scope_and_hidden_note(client):
    job = _seed_job(client, 1)  # alice's job
    _seed_applicant(client, job, 2)  # bob applied
    alice_rows = client.get("/records/job_applications", headers=ALICE).json()["rows"]
    assert {(r["user_id"], r["job_description_id"]) for r in alice_rows} == {(2, job)}
    assert all("employer_note" not in r for r in alice_rows)
    bob_rows = client.get("/records/job_applications", headers=BOB).json()["rows"]
    assert [r["user_id"] for r in bob_rows] == [2]
    assert client.get("/records/job_applications", headers=CAROL).json()["rows"] == []


def test_applicant_create_withdraw_and_forbidden(client):
    job = _seed_job(client, 1)
    r = client.post("/records/job_applications", json={"values": {"job_description_id": job, "cover_letter": "hi"}}, headers=BOB)
    assert r.status_code == 201 and r.json()["user_id"] == 2 and r.json()["status"] is None
    row_id = r.json()["id"]
    forged = {"job_description_id": job, "status": "hired"}
    assert client.post("/records/job_applications", json={"values": forged}, headers=CAROL).status_code == 422
    assert client.post("/records/job_applications", json={"values": {"job_description_id": job, "user_id": 3}}, headers=BOB).status_code == 422
    assert client.patch(f"/records/job_applications/{row_id}", json={"values": {"cover_letter": "x"}}, headers=BOB).status_code == 200
    assert client.patch(f"/records/job_applications/{row_id}", json={"values": {"status": "hired"}}, headers=BOB).status_code == 422
    # the employer may read but not withdraw somebody else's application
    assert client.delete(f"/records/job_applications/{row_id}", headers=ALICE).status_code == 404
    assert client.delete(f"/records/job_applications/{row_id}", headers=BOB).status_code == 204
