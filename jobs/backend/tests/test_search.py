from datetime import datetime, timedelta, timezone

from app.models import Posting
from tests.conftest import ALICE, BOB, post_job


def ids(response) -> list[int]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_list_requires_auth(client):
    assert client.get("/jobs").status_code == 401


def test_list_newest_first_open_only(client):
    first = post_job(client, title="First")
    second = post_job(client, title="Second", headers=BOB)
    closed = post_job(client, title="Closed")
    client.patch(f"/jobs/{closed['id']}", json={"status": "closed"}, headers=ALICE)

    assert ids(client.get("/jobs", headers=ALICE)) == [second["id"], first["id"]]


def test_expired_postings_are_excluded(client):
    job = post_job(client)
    with client.app.state.session_factory() as session:
        session.get(Posting, job["id"]).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()

    assert ids(client.get("/jobs", headers=ALICE)) == []
    detail = client.get(f"/jobs/{job['id']}", headers=BOB).json()
    assert detail["expired"] is True


def test_filters(client):
    remote = post_job(client, title="A", remote=True, location="Paris", tags=["go"],
                      salary_min=100, salary_max=200)
    contract = post_job(client, title="B", employment_type="contract", location="Rome",
                        tags=["rust"], salary_min=500, salary_max=900)

    assert ids(client.get("/jobs?remote=true", headers=BOB)) == [remote["id"]]
    assert ids(client.get("/jobs?remote=false", headers=BOB)) == [contract["id"]]
    assert ids(client.get("/jobs?type=contract", headers=BOB)) == [contract["id"]]
    assert ids(client.get("/jobs?location=par", headers=BOB)) == [remote["id"]]
    assert ids(client.get("/jobs?tag=RUST", headers=BOB)) == [contract["id"]]
    assert ids(client.get("/jobs?min_salary=300", headers=BOB)) == [contract["id"]]
    assert ids(client.get("/jobs?min_salary=1000", headers=BOB)) == []


def test_invalid_filters_rejected(client):
    for query in ["type=bogus", "limit=0", "limit=51", "min_salary=-1", "min_salary=99999999999999999999",
                  "min_salary=10000000001","q=" + "x" * 101,
                  "cursor=garbage", "tag=<b>", "remote=maybe"]:
        assert client.get(f"/jobs?{query}", headers=ALICE).status_code == 422, query


def test_like_wildcards_in_query_are_literal(client):
    post_job(client, title="Plain title")
    assert ids(client.get("/jobs?q=%25", headers=ALICE)) == []
    assert ids(client.get("/jobs?q=_", headers=ALICE)) == []


def test_relevance_title_over_tag_over_description(client):
    desc = post_job(client, title="Other", tags=["misc"], description="we use python daily")
    tag = post_job(client, title="Other2", tags=["python"], description="nothing")
    title = post_job(client, title="Python developer", tags=["misc"], description="nothing")
    post_job(client, title="Unrelated", tags=["misc"], description="nothing")

    assert ids(client.get("/jobs?q=python", headers=BOB)) == [
        title["id"],
        tag["id"],
        desc["id"],
    ]


def test_relevance_ties_are_newest_first(client):
    older = post_job(client, title="python one")
    newer = post_job(client, title="python two")
    assert ids(client.get("/jobs?q=python", headers=BOB)) == [newer["id"], older["id"]]


def test_cursor_pagination_without_query(client):
    created = [post_job(client, title=f"Job {i}")["id"] for i in range(5)]
    page1 = client.get("/jobs?limit=2", headers=BOB).json()
    page2 = client.get(f"/jobs?limit=2&cursor={page1['next_cursor']}", headers=BOB).json()
    page3 = client.get(f"/jobs?limit=2&cursor={page2['next_cursor']}", headers=BOB).json()

    seen = [i["id"] for p in (page1, page2, page3) for i in p["items"]]
    assert seen == list(reversed(created))
    assert page3["next_cursor"] is None


def test_cursor_pagination_with_ranking(client):
    expected = [
        post_job(client, title="python a")["id"],
        post_job(client, title="x", tags=["python"])["id"],
        post_job(client, title="y", tags=["misc"], description="python")["id"],
    ]
    first = client.get("/jobs?q=python&limit=1", headers=BOB).json()
    second = client.get(f"/jobs?q=python&limit=1&cursor={first['next_cursor']}", headers=BOB).json()
    third = client.get(f"/jobs?q=python&limit=5&cursor={second['next_cursor']}", headers=BOB).json()

    assert [first["items"][0]["id"], second["items"][0]["id"], third["items"][0]["id"]] == expected
    assert third["next_cursor"] is None


def test_applied_and_saved_flags_are_per_caller(client):
    job = post_job(client)
    client.post(f"/jobs/{job['id']}/apply", json={}, headers=BOB)
    client.put(f"/jobs/{job['id']}/save", headers=BOB)

    bob_item = client.get("/jobs", headers=BOB).json()["items"][0]
    alice_item = client.get("/jobs", headers=ALICE).json()["items"][0]

    assert (bob_item["applied"], bob_item["saved"]) == (True, True)
    assert (alice_item["applied"], alice_item["saved"]) == (False, False)
    assert bob_item["application_count"] is None
    assert alice_item["application_count"] == 1
    assert "description" not in bob_item


def test_summary_snippet_is_truncated(client):
    post_job(client, description="x" * 5000)
    item = client.get("/jobs", headers=BOB).json()["items"][0]
    assert len(item["snippet"]) <= 200
