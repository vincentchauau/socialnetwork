import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_course, make_lesson, make_quiz


def test_create_lesson_owner_only(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    url = f"/courses/{course['id']}/lessons"
    assert client.post(url, json={"title": "x"}).status_code == 401
    assert client.post(url, json={"title": "x"}, headers=bob).status_code == 403
    first = make_lesson(client, alice, course["id"], video_url="https://example.com/v")
    second = make_lesson(client, alice, course["id"], title="Two")
    assert (first["position"], second["position"]) == (1, 2)
    assert first["video_url"] == "https://example.com/v"


def test_create_lesson_on_draft_is_404_for_others(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice, published=False)
    url = f"/courses/{course['id']}/lessons"
    assert client.post(url, json={"title": "x"}, headers=bob).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "x", "content": "c" * 20001},
        {"title": "x", "video_url": "http://example.com/v"},
        {"title": "x", "video_url": "javascript:alert(1)"},
        {"title": "x", "video_url": "https://"},
        {"title": "x", "video_url": "https://user:pw@example.com/v"},
        {"title": "x", "video_url": "https://exa mple.com"},
        {"title": "x", "video_url": "https://example.com/" + "a" * 500},
        {"title": "x", "position": 3},
    ],
)
def test_lesson_validation(client: TestClient, alice, body) -> None:
    course = make_course(client, alice)
    assert client.post(f"/courses/{course['id']}/lessons", json=body, headers=alice).status_code == 422


def test_content_max_length_accepted(client: TestClient, alice) -> None:
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"], content="c" * 20000)
    assert len(lesson["content"]) == 20000


def test_lesson_quota(client: TestClient, alice, monkeypatch) -> None:
    from app import lessons

    monkeypatch.setattr(lessons, "MAX_LESSONS_PER_COURSE", 1)
    course = make_course(client, alice)
    make_lesson(client, alice, course["id"])
    response = client.post(f"/courses/{course['id']}/lessons", json={"title": "x"}, headers=alice)
    assert response.status_code == 409


def test_content_requires_enrolment(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"], content="LESSON TEXT")
    url = f"/courses/{course['id']}/lessons/{lesson['id']}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=bob).status_code == 403
    assert client.get(url, headers=alice).json()["content"] == "LESSON TEXT"
    client.post(f"/courses/{course['id']}/enroll", headers=bob)
    seen = client.get(url, headers=bob).json()
    assert seen["content"] == "LESSON TEXT"
    assert seen["completed"] is False


def test_lesson_of_other_course_is_404(client: TestClient, alice) -> None:
    one = make_course(client, alice)
    two = make_course(client, alice, title="Two")
    lesson = make_lesson(client, alice, one["id"])
    assert client.get(f"/courses/{two['id']}/lessons/{lesson['id']}", headers=alice).status_code == 404
    assert client.get(f"/courses/{one['id']}/lessons/999", headers=alice).status_code == 404


def test_update_and_delete_lesson(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"])
    url = f"/courses/{course['id']}/lessons/{lesson['id']}"
    assert client.patch(url, json={"title": "n"}, headers=bob).status_code == 403
    updated = client.patch(url, json={"title": "New", "video_url": None}, headers=alice).json()
    assert updated["title"] == "New"
    assert client.patch(url, json={"video_url": "http://x.io"}, headers=alice).status_code == 422
    cleared = client.patch(url, json={"video_url": "https://a.io/v"}, headers=alice).json()
    assert cleared["video_url"] == "https://a.io/v"
    assert client.patch(url, json={"video_url": None}, headers=alice).json()["video_url"] is None
    assert client.delete(url, headers=bob).status_code == 403
    assert client.delete(url, headers=alice).status_code == 204
    assert client.get(url, headers=alice).status_code == 404


def test_delete_lesson_closes_position_gap(client: TestClient, alice) -> None:
    course = make_course(client, alice)
    a = make_lesson(client, alice, course["id"], title="A")
    make_lesson(client, alice, course["id"], title="B")
    client.delete(f"/courses/{course['id']}/lessons/{a['id']}", headers=alice)
    outline = client.get(f"/courses/{course['id']}").json()["lessons"]
    assert [(lesson["title"], lesson["position"]) for lesson in outline] == [("B", 1)]


def test_reorder(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    ids = [make_lesson(client, alice, course["id"], title=t)["id"] for t in "ABC"]
    url = f"/courses/{course['id']}/lessons/order"
    assert client.put(url, json={"lesson_ids": ids[::-1]}, headers=bob).status_code == 403
    assert client.put(url, json={"lesson_ids": ids[::-1]}).status_code == 401
    result = client.put(url, json={"lesson_ids": ids[::-1]}, headers=alice).json()
    assert [lesson["title"] for lesson in result] == ["C", "B", "A"]
    outline = client.get(f"/courses/{course['id']}").json()["lessons"]
    assert [lesson["title"] for lesson in outline] == ["C", "B", "A"]
    assert [lesson["position"] for lesson in outline] == [1, 2, 3]


@pytest.mark.parametrize("ids", [[1], [1, 1, 2], [1, 2, 99], []])
def test_reorder_must_be_exact_permutation(client: TestClient, alice, ids) -> None:
    course = make_course(client, alice)
    make_lesson(client, alice, course["id"])
    make_lesson(client, alice, course["id"])
    url = f"/courses/{course['id']}/lessons/order"
    assert client.put(url, json={"lesson_ids": ids}, headers=alice).status_code == 422


def test_outline_flags_quiz(client: TestClient, alice) -> None:
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"])
    make_quiz(client, alice, course["id"], lesson["id"])
    outline = client.get(f"/courses/{course['id']}").json()["lessons"]
    assert outline[0]["has_quiz"] is True
