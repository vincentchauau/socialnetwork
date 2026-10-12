import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_cookie, make_course, make_lesson


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_create_requires_auth(client: TestClient) -> None:
    assert client.post("/courses", json={"title": "x"}).status_code == 401


def test_create_course_normalises_tags_and_owner(client: TestClient, alice) -> None:
    course = make_course(client, alice, tags=["Python", " python ", "Web Dev"], level="advanced")
    assert course["owner_username"] == "alice"
    assert course["is_owner"] is True
    assert course["tags"] == ["python", "web dev"]
    assert course["level"] == "advanced"
    assert course["lessons"] == []


def test_username_in_body_is_rejected(client: TestClient, alice) -> None:
    response = client.post(
        "/courses", json={"title": "x", "owner_username": "mallory"}, headers=alice
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "x" * 121},
        {"title": "ok", "summary": "s" * 1001},
        {"title": "ok", "level": "expert"},
        {"title": "ok", "tags": [f"t{i}" for i in range(11)]},
        {"title": "ok", "tags": ["bad$tag"]},
        {"title": "ok", "tags": ["x" * 31]},
        {"title": "   "},
    ],
)
def test_create_validation(client: TestClient, alice, body) -> None:
    assert client.post("/courses", json=body, headers=alice).status_code == 422


def test_course_quota(client: TestClient, alice, monkeypatch) -> None:
    from app import courses

    monkeypatch.setattr(courses, "MAX_COURSES_PER_USER", 1)
    make_course(client, alice)
    response = client.post("/courses", json={"title": "second"}, headers=alice)
    assert response.status_code == 409


def test_draft_hidden_from_others(client: TestClient, alice, bob) -> None:
    draft = make_course(client, alice, published=False)
    url = f"/courses/{draft['id']}"
    assert client.get(url, headers=alice).status_code == 200
    assert client.get(url, headers=bob).status_code == 404
    assert client.get(url).status_code == 404
    assert client.patch(url, json={"title": "x"}, headers=bob).status_code == 404
    assert client.delete(url, headers=bob).status_code == 404


def test_published_course_is_public_outline(client: TestClient, alice) -> None:
    course = make_course(client, alice)
    make_lesson(client, alice, course["id"], title="Secret lesson", content="SECRET")
    body = client.get(f"/courses/{course['id']}").json()
    assert body["lessons"][0]["title"] == "Secret lesson"
    assert "SECRET" not in client.get(f"/courses/{course['id']}").text
    assert body["enrolled"] is False
    assert body["is_owner"] is False


def test_get_missing_course(client: TestClient) -> None:
    assert client.get("/courses/999").status_code == 404
    assert client.get("/courses/abc").status_code == 422


def test_patch_owner_only(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    url = f"/courses/{course['id']}"
    assert client.patch(url, json={"title": "x"}, headers=bob).status_code == 403
    assert client.patch(url, json={"title": "x"}).status_code == 401
    ok = client.patch(
        url, json={"title": "New", "tags": ["a"], "published": False, "level": "intermediate"},
        headers=alice,
    )
    assert ok.status_code == 200
    assert ok.json()["title"] == "New"
    assert ok.json()["tags"] == ["a"]
    assert ok.json()["published"] is False
    assert client.patch(url, json={"title": ""}, headers=alice).status_code == 422
    assert client.patch(url, json={"summary": "only"}, headers=alice).json()["title"] == "New"


def test_delete_cascades(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"])
    client.post(f"/courses/{course['id']}/enroll", headers=bob)
    url = f"/courses/{course['id']}"
    assert client.delete(url, headers=bob).status_code == 403
    assert client.delete(url, headers=alice).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get(f"{url}/lessons/{lesson['id']}", headers=alice).status_code == 404
    assert client.get("/me/courses", headers=bob).json() == []


def test_list_only_published_with_filters(client: TestClient, alice, bob) -> None:
    make_course(client, alice, title="Python basics", tags=["python"], level="beginner")
    make_course(client, alice, title="Rust deep", tags=["rust"], level="advanced")
    make_course(client, alice, title="Hidden", published=False)
    titles = lambda r: sorted(c["title"] for c in r.json()["items"])  # noqa: E731
    assert titles(client.get("/courses")) == ["Python basics", "Rust deep"]
    assert titles(client.get("/courses", params={"q": "PYTHON"})) == ["Python basics"]
    assert titles(client.get("/courses", params={"level": "advanced"})) == ["Rust deep"]
    assert titles(client.get("/courses", params={"tag": "Rust"})) == ["Rust deep"]
    assert titles(client.get("/courses", params={"q": "%"})) == []
    assert titles(client.get("/courses", headers=bob)) == ["Python basics", "Rust deep"]


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 51}, {"level": "x"}, {"cursor": 0}, {"q": "x" * 101}]
)
def test_list_validation(client: TestClient, params) -> None:
    assert client.get("/courses", params=params).status_code == 422


def test_list_pagination(client: TestClient, alice) -> None:
    for i in range(5):
        make_course(client, alice, title=f"C{i}")
    first = client.get("/courses", params={"limit": 2}).json()
    assert [c["title"] for c in first["items"]] == ["C4", "C3"]
    second = client.get("/courses", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [c["title"] for c in second["items"]] == ["C2", "C1"]
    last = client.get("/courses", params={"limit": 2, "cursor": second["next_cursor"]}).json()
    assert [c["title"] for c in last["items"]] == ["C0"]
    assert last["next_cursor"] is None


def test_list_shows_counts_and_my_progress(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"])
    make_lesson(client, alice, course["id"], title="Two")
    client.post(f"/courses/{course['id']}/enroll", headers=bob)
    client.put(f"/courses/{course['id']}/lessons/{lesson['id']}/complete", headers=bob)
    mine = client.get("/courses", headers=bob).json()["items"][0]
    assert mine["enrolment_count"] == 1
    assert mine["lesson_count"] == 2
    assert mine["enrolled"] is True
    assert mine["progress_percent"] == 50
    anon = client.get("/courses").json()["items"][0]
    assert anon["enrolled"] is False
    assert anon["progress_percent"] == 0


def test_authored_lists_own_drafts(client: TestClient, alice, bob) -> None:
    make_course(client, alice, title="Mine", published=False)
    make_course(client, bob, title="Theirs")
    assert [c["title"] for c in client.get("/me/authored", headers=alice).json()] == ["Mine"]
    assert client.get("/me/authored").status_code == 401


def test_invalid_cookie_on_optional_route_is_anonymous(client: TestClient) -> None:
    make_course(client, auth_cookie())
    bad = {"Cookie": "sn_token=garbage"}
    assert client.get("/courses", headers=bad).status_code == 200
