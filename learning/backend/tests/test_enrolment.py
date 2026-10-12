from fastapi.testclient import TestClient

from tests.conftest import make_course, make_lesson


def _course_with_lessons(client: TestClient, owner, count: int = 2):
    course = make_course(client, owner)
    lessons = [make_lesson(client, owner, course["id"], title=f"L{i}") for i in range(count)]
    return course, lessons


def test_enroll_idempotent(client: TestClient, alice, bob) -> None:
    course, _ = _course_with_lessons(client, alice)
    url = f"/courses/{course['id']}/enroll"
    assert client.post(url).status_code == 401
    first = client.post(url, headers=bob)
    second = client.post(url, headers=bob)
    assert first.status_code == second.status_code == 200
    assert first.json()["enrolled_at"] == second.json()["enrolled_at"]
    detail = client.get(f"/courses/{course['id']}", headers=bob).json()
    assert detail["enrolment_count"] == 1
    assert detail["enrolled"] is True


def test_enroll_draft_or_missing_is_404(client: TestClient, alice, bob) -> None:
    draft = make_course(client, alice, published=False)
    assert client.post(f"/courses/{draft['id']}/enroll", headers=bob).status_code == 404
    assert client.post("/courses/999/enroll", headers=bob).status_code == 404


def test_unenroll_clears_progress_and_is_idempotent(client: TestClient, alice, bob) -> None:
    course, lessons = _course_with_lessons(client, alice)
    base = f"/courses/{course['id']}"
    client.post(f"{base}/enroll", headers=bob)
    client.put(f"{base}/lessons/{lessons[0]['id']}/complete", headers=bob)
    assert client.delete(f"{base}/enroll", headers=bob).status_code == 204
    assert client.delete(f"{base}/enroll", headers=bob).status_code == 204
    assert client.delete(f"{base}/enroll").status_code == 401
    assert client.get(f"{base}/progress", headers=bob).status_code == 404
    client.post(f"{base}/enroll", headers=bob)
    assert client.get(f"{base}/progress", headers=bob).json()["percent"] == 0
    assert client.get(f"{base}/lessons/{lessons[0]['id']}", headers=bob).json()["completed"] is False


def test_my_courses(client: TestClient, alice, bob) -> None:
    course, lessons = _course_with_lessons(client, alice, 4)
    base = f"/courses/{course['id']}"
    assert client.get("/me/courses").status_code == 401
    assert client.get("/me/courses", headers=bob).json() == []
    client.post(f"{base}/enroll", headers=bob)
    client.put(f"{base}/lessons/{lessons[0]['id']}/complete", headers=bob)
    items = client.get("/me/courses", headers=bob).json()
    assert len(items) == 1
    assert items[0]["title"] == course["title"]
    assert items[0]["progress_percent"] == 25
    assert items[0]["enrolled"] is True
    client.patch(base, json={"published": False}, headers=alice)
    assert client.get("/me/courses", headers=bob).json() == []


def test_complete_requires_enrolment(client: TestClient, alice, bob) -> None:
    course, lessons = _course_with_lessons(client, alice)
    url = f"/courses/{course['id']}/lessons/{lessons[0]['id']}/complete"
    assert client.put(url).status_code == 401
    assert client.put(url, headers=bob).status_code == 404
    assert client.delete(url, headers=bob).status_code == 404
    assert client.put(f"/courses/{course['id']}/lessons/999/complete", headers=bob).status_code in (404,)


def test_complete_and_uncomplete(client: TestClient, alice, bob) -> None:
    course, lessons = _course_with_lessons(client, alice, 3)
    base = f"/courses/{course['id']}"
    client.post(f"{base}/enroll", headers=bob)
    url = f"{base}/lessons/{lessons[0]['id']}/complete"
    first = client.put(url, headers=bob).json()
    again = client.put(url, headers=bob).json()
    assert first == again
    assert first["percent"] == 33
    assert first["completed_lesson_ids"] == [lessons[0]["id"]]
    assert first["total_lessons"] == 3
    assert first["completed"] is False
    cleared = client.delete(url, headers=bob).json()
    assert cleared["percent"] == 0
    assert client.delete(url, headers=bob).json()["percent"] == 0


def test_complete_unknown_lesson_when_enrolled(client: TestClient, alice, bob) -> None:
    course, _ = _course_with_lessons(client, alice)
    client.post(f"/courses/{course['id']}/enroll", headers=bob)
    assert client.put(f"/courses/{course['id']}/lessons/999/complete", headers=bob).status_code == 404


def test_progress_endpoint(client: TestClient, alice, bob) -> None:
    course, lessons = _course_with_lessons(client, alice, 2)
    base = f"/courses/{course['id']}"
    assert client.get(f"{base}/progress").status_code == 401
    assert client.get(f"{base}/progress", headers=bob).status_code == 404
    client.post(f"{base}/enroll", headers=bob)
    for lesson in lessons:
        client.put(f"{base}/lessons/{lesson['id']}/complete", headers=bob)
    progress = client.get(f"{base}/progress", headers=bob).json()
    assert progress["percent"] == 100
    assert progress["completed"] is True
    assert progress["quizzes_total"] == 0


def test_progress_ignores_deleted_lessons(client: TestClient, alice, bob) -> None:
    course, lessons = _course_with_lessons(client, alice, 2)
    base = f"/courses/{course['id']}"
    client.post(f"{base}/enroll", headers=bob)
    client.put(f"{base}/lessons/{lessons[0]['id']}/complete", headers=bob)
    client.delete(f"{base}/lessons/{lessons[0]['id']}", headers=alice)
    progress = client.get(f"{base}/progress", headers=bob).json()
    assert progress["total_lessons"] == 1
    assert progress["percent"] == 0


def test_owner_cannot_enroll_in_own_course(client: TestClient, alice) -> None:
    course, _ = _course_with_lessons(client, alice)
    assert client.post(f"/courses/{course['id']}/enroll", headers=alice).status_code == 403
    assert client.get(f"/courses/{course['id']}", headers=alice).json()["enrolment_count"] == 0
