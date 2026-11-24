from tests.job.conftest import ALICE, post_job


def _ids(client, **params) -> set[int]:
    items = client.get("/jobs", params=params, headers=ALICE).json()["items"]
    return {item["id"] for item in items}


def test_a_job_is_found_by_its_tag_whatever_the_case(client):
    python = post_job(client, title="A", tags=["python", "sql"])
    go = post_job(client, title="B", tags=["go"])

    assert _ids(client, tag="PYTHON") == {python["id"]}
    assert _ids(client, tag="go") == {go["id"]}


def test_a_job_is_found_by_a_skill_it_requires_or_prefers_however_it_is_written(client):
    job = post_job(
        client,
        title="C",
        skills_required=[{"name": "Node.js", "level": "advanced", "years": 3}],
        skills_preferred=[{"name": "PostgreSQL", "level": "beginner", "years": None}],
    )
    post_job(client, title="D", skills_required=[{"name": "Java", "level": "beginner", "years": None}])

    assert _ids(client, skill="nodejs") == {job["id"]}
    assert _ids(client, skill="POSTGRES") == {job["id"]}


def test_the_skills_are_suggested_from_the_catalog_without_a_count(client):
    post_job(client, title="E", skills_required=[{"name": "Kubernetes", "level": "beginner", "years": None}])

    suggestions = client.get("/skills", params={"q": "kub"}, headers=ALICE).json()
    assert [s["key"] for s in suggestions] == ["kubernetes"]
    assert "uses" not in suggestions[0]
