"""The skills of a job against the skills of a person (`sn_shared.skills`), and jobs found by skill."""

from sn_shared.testing import add_person

from tests.job.conftest import ALICE, BOB, CAROL, post_job

ASKS = {
    "skills_required": [{"name": "Python", "level": "advanced", "years": 3}, {"name": "SQL"}],
    "skills_preferred": [{"name": "Kubernetes"}],
}


def know(client, user_id, username, skills):
    add_person(client.app.state.session_factory, user_id, username, skills=skills)


def test_a_viewer_sees_how_well_their_profile_fits_the_job(client):
    job = post_job(client, **ASKS)
    know(client, 2, "bob", [{"name": "python", "level": "expert", "years": 5}, {"name": "K8s"}])
    seen = client.get(f"/jobs/{job['id']}", headers=BOB).json()["match"]
    assert seen["matched"] == ["Python"] and seen["missing"] == ["SQL"] and seen["missing_preferred"] == []
    assert seen["score"] == round((0.8 * 0.5 + 0.2 * 1) * 100)


def test_somebody_with_no_skills_in_their_profile_is_told_what_is_missing(client):
    job = post_job(client, **ASKS)
    seen = client.get(f"/jobs/{job['id']}", headers=CAROL).json()["match"]  # (not in users at all)
    assert seen["score"] == 0 and seen["missing"] == ["Python", "SQL"] and seen["missing_preferred"] == ["Kubernetes"]


def test_no_match_for_the_owner_or_for_a_job_that_asks_for_no_skills(client):
    job = post_job(client, **ASKS)
    assert client.get(f"/jobs/{job['id']}", headers=ALICE).json()["match"] is None
    plain = post_job(client)
    assert client.get(f"/jobs/{plain['id']}", headers=BOB).json()["match"] is None


def test_the_employer_sees_how_well_the_resume_of_each_applicant_fits(client):
    job = post_job(client, **ASKS)
    resume = {"skills": [{"name": "Python", "level": "advanced", "years": 4}, {"name": "SQL", "level": "beginner"}]}
    client.post(f"/jobs/{job['id']}/apply", json={"resume": resume}, headers=BOB)
    client.post(f"/jobs/{job['id']}/apply", json={}, headers=CAROL)  # no resume
    listed = {a["applicant_username"]: a for a in client.get(f"/jobs/{job['id']}/applications", headers=ALICE).json()}
    assert listed["bob"]["match"]["matched"] == ["Python", "SQL"] and listed["bob"]["match"]["score"] == round((0.8 * 1 + 0.2 * 0) * 100)
    assert listed["carol"]["match"]["score"] == 0 and listed["carol"]["match"]["missing"] == ["Python", "SQL"]
    changed = client.patch(f"/applications/{listed['bob']['id']}", json={"status": "reviewing"}, headers=ALICE).json()
    assert changed["match"]["score"] == listed["bob"]["match"]["score"]


def test_jobs_are_found_by_a_skill_however_it_is_written(client):
    job = post_job(client, **ASKS)
    other = post_job(client, skills_required=[{"name": "Go"}])
    ids = lambda **params: [j["id"] for j in client.get("/jobs", params=params, headers=BOB).json()["items"]]  # noqa: E731
    assert ids(skill="python") == [job["id"]] and ids(skill=" PYTHON ") == [job["id"]]
    assert ids(skill="k8s") == [job["id"]]  # only liked, and another way to write it
    assert ids(skill="golang") == [other["id"]]
    assert ids(skill="cobol") == []
    client.patch(f"/jobs/{job['id']}", json={"skills_required": [{"name": "Cobol"}], "skills_preferred": []}, headers=ALICE)
    assert ids(skill="python") == [] and ids(skill="cobol") == [job["id"]]
    client.delete(f"/jobs/{job['id']}", headers=ALICE)
    assert ids(skill="cobol") == []


def test_the_skills_a_job_asks_for_are_suggested_to_those_who_write_one(client):
    post_job(client, **ASKS)
    names = [s["name"] for s in client.get("/skills", params={"q": "p"}, headers=BOB).json()]
    assert names == ["Python"]
    assert client.get("/skills", headers=BOB).status_code == 200 and client.get("/skills").status_code == 401
