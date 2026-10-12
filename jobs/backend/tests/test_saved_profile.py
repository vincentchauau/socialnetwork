import pytest

from tests.conftest import ALICE, BOB, post_job


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


def test_profile_defaults_when_missing(client):
    response = client.get("/me/profile", headers=BOB)
    assert response.status_code == 200
    assert response.json() == {
        "username": "bob",
        "headline": "",
        "skills": [],
        "about": "",
        "open_to_work": False,
    }
    assert client.get("/me/profile").status_code == 401


def test_profile_upsert(client):
    body = {"headline": "Engineer", "skills": ["Python", "sql"], "about": "About me",
            "open_to_work": True}
    first = client.put("/me/profile", json=body, headers=BOB)
    second = client.put("/me/profile", json={**body, "headline": "Lead"}, headers=BOB)

    assert first.status_code == 200
    assert second.json()["headline"] == "Lead"
    assert client.get("/me/profile", headers=BOB).json()["skills"] == ["Python", "sql"]
    assert client.get("/me/profile", headers=ALICE).json()["headline"] == ""


def test_profile_username_comes_from_token(client):
    response = client.put("/me/profile", json={"username": "evil", "user_id": 5}, headers=BOB)
    assert response.json()["username"] == "bob"


@pytest.mark.parametrize(
    "body",
    [
        {"headline": "x" * 121},
        {"about": "x" * 2001},
        {"skills": ["s"] * 21},
        {"skills": [""]},
        {"skills": ["x" * 41]},
        {"open_to_work": "maybe"},
    ],
)
def test_profile_validation(client, body):
    assert client.put("/me/profile", json=body, headers=BOB).status_code == 422


def test_profile_put_requires_auth(client):
    assert client.put("/me/profile", json={}).status_code == 401
