from datetime import datetime, timedelta, timezone

import pytest

from tests.job.conftest import ALICE, BOB, job_body, post_job


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_posting_takes_owner_from_token(client):
    response = client.post(
        "/jobs", json=job_body(owner_username="mallory", owner_id=99), headers=ALICE
    )

    assert response.status_code == 201
    body = response.json()
    assert body["owner_username"] == "alice"
    assert body["is_owner"] is True
    assert body["status"] == "open"
    assert body["tags"] == ["fastapi", "python"]  # the tags are kept sorted
    assert body["application_count"] == 0
    assert "owner_id" not in body


def test_create_requires_auth(client):
    assert client.post("/jobs", json=job_body()).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "x" * 121},
        {"company": ""},
        {"company": "x" * 121},
        {"location": "x" * 121},
        {"employment_type": "slave"},
        {"salary_min": -1},
        {"salary_min": 10, "salary_max": 5},
        {"currency": "usd"},
        {"currency": "DOLLARS"},
        {"description": "x" * 10001},
        {"tags": [str(i) for i in range(11)]},
        {"tags": ["<script>"]},
        {"tags": [""]},
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"expires_at": "not-a-date"},
    ],
)
def test_create_validation(client, overrides):
    response = client.post("/jobs", json=job_body(**overrides), headers=ALICE)
    assert response.status_code == 422


def test_tags_are_normalised_and_deduplicated(client):
    job = post_job(client, tags=["Python", " python ", "AWS"])
    assert job["tags"] == ["aws", "python"]


def test_salary_and_expiry_round_trip(client):
    expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    job = post_job(
        client, salary_min=50000, salary_max=70000, currency="EUR", expires_at=expires
    )
    fetched = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert (fetched["salary_min"], fetched["salary_max"], fetched["currency"]) == (
        50000,
        70000,
        "EUR",
    )
    assert fetched["expires_at"] is not None
    assert fetched["expired"] is False


def test_description_is_returned_verbatim(client):
    job = post_job(client, description="<b>hi</b>\n\nline")
    assert client.get(f"/jobs/{job['id']}", headers=BOB).json()["description"] == "<b>hi</b>\n\nline"


def test_get_requires_auth(client):
    job = post_job(client)
    assert client.get(f"/jobs/{job['id']}").status_code == 401


def test_get_missing_is_404(client):
    assert client.get("/jobs/999", headers=ALICE).status_code == 404


def test_non_owner_does_not_see_application_count(client):
    job = post_job(client)
    other = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert other["application_count"] is None
    assert other["is_owner"] is False


def test_closed_posting_hidden_from_others_but_visible_to_owner(client):
    job = post_job(client)
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)

    assert client.get(f"/jobs/{job['id']}", headers=BOB).status_code == 404
    assert client.get(f"/jobs/{job['id']}", headers=ALICE).json()["status"] == "closed"


def test_update_by_owner(client):
    job = post_job(client, salary_min=1, salary_max=2)

    response = client.patch(
        f"/jobs/{job['id']}",
        json={"title": "Staff Engineer", "remote": True, "salary_max": None},
        headers=ALICE,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["title"] == "Staff Engineer"
    assert body["remote"] is True
    assert body["salary_max"] is None
    assert body["company"] == "Acme"


def test_update_tags_normalised(client):
    job = post_job(client)
    response = client.patch(
        f"/jobs/{job['id']}", json={"tags": ["Go", "go", "K8s"]}, headers=ALICE
    )
    assert response.json()["tags"] == ["go", "k8s"]
    cleared = client.patch(f"/jobs/{job['id']}", json={"tags": []}, headers=ALICE)
    assert cleared.json()["tags"] == []


def test_update_by_non_owner_not_found(client):
    job = post_job(client)
    response = client.patch(f"/jobs/{job['id']}", json={"title": "Hacked"}, headers=BOB)
    assert response.status_code == 404
    assert client.get(f"/jobs/{job['id']}", headers=ALICE).json()["title"] == "Backend Engineer"


def test_update_missing_is_404(client):
    assert client.patch("/jobs/9", json={"title": "x"}, headers=ALICE).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"title": None},
        {"title": ""},
        {"status": "weird"},
        {"salary_min": 100, "salary_max": 10},
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"tags": ["a"] * 11},
    ],
)
def test_update_validation(client, payload):
    job = post_job(client)
    assert client.patch(f"/jobs/{job['id']}", json=payload, headers=ALICE).status_code == 422


def test_update_salary_merge_checked_against_existing(client):
    job = post_job(client, salary_min=10, salary_max=20)
    response = client.patch(f"/jobs/{job['id']}", json={"salary_min": 30}, headers=ALICE)
    assert response.status_code == 422


def test_reopen_and_clear_expiry(client):
    job = post_job(client)
    client.patch(f"/jobs/{job['id']}", json={"status": "closed"}, headers=ALICE)
    response = client.patch(
        f"/jobs/{job['id']}", json={"status": "open", "expires_at": None}, headers=ALICE
    )
    assert response.json()["status"] == "open"
    assert response.json()["expires_at"] is None


def test_delete_by_owner_removes_applications_and_saves(client):
    job = post_job(client)
    client.post(f"/jobs/{job['id']}/apply", json={}, headers=BOB)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)

    assert client.delete(f"/jobs/{job['id']}", headers=ALICE).status_code == 204

    assert client.get(f"/jobs/{job['id']}", headers=ALICE).status_code == 404
    assert client.get("/me/applications", headers=BOB).json() == []
    assert client.get("/me/saved", headers=BOB).json() == []


def test_delete_by_non_owner_not_found(client):
    job = post_job(client)
    assert client.delete(f"/jobs/{job['id']}", headers=BOB).status_code == 404
    assert client.delete("/jobs/77", headers=BOB).status_code == 404
    assert client.delete(f"/jobs/{job['id']}").status_code == 401


def test_my_postings_lists_only_own_with_counts(client):
    mine = post_job(client)
    post_job(client, headers=BOB, title="Bobs job")
    client.post(f"/jobs/{mine['id']}/apply", json={}, headers=BOB)
    client.patch(f"/jobs/{mine['id']}", json={"status": "closed"}, headers=ALICE)

    response = client.get("/me/jobs", headers=ALICE)

    assert response.status_code == 200
    items = response.json()
    assert [item["id"] for item in items] == [mine["id"]]
    assert items[0]["application_count"] == 1
    assert items[0]["status"] == "closed"
    assert client.get("/me/jobs").status_code == 401


def test_open_posting_limit_per_user(client, monkeypatch):
    import api.job.job_descriptions as postings

    monkeypatch.setattr(postings, "MAX_OPEN_JOBS_PER_USER", 2)
    post_job(client)
    post_job(client)
    response = client.post("/jobs", json=job_body(), headers=ALICE)
    assert response.status_code == 409
    assert client.post("/jobs", json=job_body(), headers=BOB).status_code == 201


STRUCTURED = {
    "department": "Platform",
    "seniority": "senior",
    "openings": 2,
    "experience_min_years": 5,
    "education_min": "bachelor",
    "skills_required": [{"name": "Python", "level": "advanced", "years": 4}, {"name": "SQL"}],
    "skills_preferred": [{"name": "Kubernetes", "level": "intermediate"}],
    "languages": [{"language": "English", "proficiency": "fluent"}],
    "responsibilities": ["Design services", "Review code"],
    "benefits": ["Health insurance"],
    "salary_period": "month",
}


def test_a_job_keeps_what_it_asks_of_a_person_as_structure(client):
    job = post_job(client, **STRUCTURED)
    assert job["seniority"] == "senior" and job["openings"] == 2 and job["department"] == "Platform"
    assert job["experience_min_years"] == 5 and job["education_min"] == "bachelor"
    assert job["skills_required"][0] == {"name": "Python", "level": "advanced", "years": 4}
    assert job["skills_required"][1] == {"name": "SQL", "level": None, "years": None}
    assert job["languages"] == [{"language": "English", "proficiency": "fluent"}]
    assert job["responsibilities"] == ["Design services", "Review code"] and job["benefits"] == ["Health insurance"]
    again = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert again["skills_preferred"] == [{"name": "Kubernetes", "level": "intermediate", "years": None}]
    assert again["salary_period"] == "month"


def test_a_job_without_the_structure_has_empty_lists(client):
    job = post_job(client)
    assert job["skills_required"] == [] and job["languages"] == [] and job["seniority"] is None and job["openings"] == 1


def test_the_structure_can_be_changed_and_cleared(client):
    job = post_job(client, **STRUCTURED)
    changed = client.patch(
        f"/jobs/{job['id']}",
        json={"skills_required": [{"name": "Go"}], "seniority": None, "experience_min_years": 8},
        headers=ALICE,
    ).json()
    assert [s["name"] for s in changed["skills_required"]] == ["Go"]
    assert changed["seniority"] is None and changed["experience_min_years"] == 8
    assert changed["languages"] == job["languages"]  # what was not sent is kept
    assert client.patch(f"/jobs/{job['id']}", json={"skills_required": None}, headers=ALICE).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("seniority", "wizard"), ("education_min", "phd-ish"), ("openings", 0), ("openings", 1001),
        ("experience_min_years", -1), ("salary_period", "week"), ("employment_type", "volunteer"),
        ("skills_required", [{"name": ""}]), ("skills_required", [{"name": "x", "level": "godlike"}]),
        ("skills_required", [{"name": "x"}] * 31), ("languages", [{"language": "x", "proficiency": "alien"}]),
        ("responsibilities", [""]), ("benefits", ["x" * 301]),
    ],
)
def test_the_structure_is_validated(client, field, value):
    assert client.post("/jobs", json=job_body(**{field: value}), headers=ALICE).status_code == 422


def test_the_kinds_of_work_are_those_of_the_profile_of_an_account(client):
    for kind in ("full_time", "part_time", "contract", "internship", "freelance", "other"):
        assert client.post("/jobs", json=job_body(employment_type=kind), headers=ALICE).status_code == 201


def test_a_draft_is_seen_only_by_its_owner_and_is_not_found_by_search(client):
    job = post_job(client, status="draft")
    assert job["status"] == "draft"
    assert client.get(f"/jobs/{job['id']}", headers=ALICE).status_code == 200
    assert client.get(f"/jobs/{job['id']}", headers=BOB).status_code == 404
    assert client.get("/jobs", headers=BOB).json()["items"] == []
    client.patch(f"/jobs/{job['id']}", json={"status": "open"}, headers=ALICE)
    assert len(client.get("/jobs", headers=BOB).json()["items"]) == 1


@pytest.mark.parametrize("state", ["paused", "closed", "filled"])
def test_a_job_that_is_not_open_is_hidden_and_takes_no_applications(client, state):
    job = post_job(client)
    client.patch(f"/jobs/{job['id']}", json={"status": state}, headers=ALICE)
    assert client.get("/jobs", headers=BOB).json()["items"] == []
    assert client.post(f"/jobs/{job['id']}/apply", json={}, headers=BOB).status_code == 404
