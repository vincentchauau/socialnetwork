from fastapi.testclient import TestClient

from tests.conftest import make_course, make_lesson, make_quiz


def _answers(quiz: dict, right: bool) -> dict:
    answers = []
    for question in quiz["questions"]:
        right_texts = ("4",) if question["text"] == "2+2?" else ("2", "3")
        correct = [o["id"] for o in question["options"] if o["text"] in right_texts]
        wrong = [question["options"][0]["id"]]
        answers.append({"question_id": question["id"], "option_ids": correct if right else wrong})
    return {"answers": answers}


def test_certificate_flow(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice, title="Certified")
    base = f"/courses/{course['id']}"
    lesson = make_lesson(client, alice, course["id"])
    other = make_lesson(client, alice, course["id"], title="Two")
    quiz = make_quiz(client, alice, course["id"], lesson["id"])
    cert_url = f"{base}/certificate"

    assert client.get(cert_url).status_code == 401
    assert client.get(cert_url, headers=bob).status_code == 404
    client.post(f"{base}/enroll", headers=bob)
    assert client.get(cert_url, headers=bob).status_code == 409

    for item in (lesson, other):
        client.put(f"{base}/lessons/{item['id']}/complete", headers=bob)
    assert client.get(cert_url, headers=bob).status_code == 409  # quiz not passed

    learner_quiz = client.get(f"/quizzes/{quiz['id']}", headers=bob).json()
    client.post(f"/quizzes/{quiz['id']}/attempts", json=_answers(learner_quiz, False), headers=bob)
    assert client.get(cert_url, headers=bob).status_code == 409
    client.post(f"/quizzes/{quiz['id']}/attempts", json=_answers(learner_quiz, True), headers=bob)

    first = client.get(cert_url, headers=bob)
    assert first.status_code == 200
    cert = first.json()
    assert cert["learner"] == "bob"
    assert cert["course"] == "Certified"
    assert len(cert["code"]) >= 16
    assert client.get(cert_url, headers=bob).json() == cert  # stable

    public = client.get(f"/certificates/{cert['code']}")
    assert public.status_code == 200
    assert set(public.json()) == {"learner", "course", "completed_at"}


def test_certificate_needs_lessons(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    client.post(f"/courses/{course['id']}/enroll", headers=bob)
    assert client.get(f"/courses/{course['id']}/certificate", headers=bob).status_code == 409


def test_public_lookup_unknown_and_malformed(client: TestClient) -> None:
    assert client.get("/certificates/" + "a" * 22).status_code == 404
    assert client.get("/certificates/short").status_code == 422
    assert client.get("/certificates/" + "a" * 65).status_code == 422
    assert client.get("/certificates/bad%20code%20bad%20code%20bad%20code").status_code == 422


def test_certificate_removed_with_course(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    base = f"/courses/{course['id']}"
    lesson = make_lesson(client, alice, course["id"])
    quiz = make_quiz(client, alice, course["id"], lesson["id"])
    client.post(f"{base}/enroll", headers=bob)
    client.put(f"{base}/lessons/{lesson['id']}/complete", headers=bob)
    learner_quiz = client.get(f"/quizzes/{quiz['id']}", headers=bob).json()
    client.post(f"/quizzes/{quiz['id']}/attempts", json=_answers(learner_quiz, True), headers=bob)
    code = client.get(f"{base}/certificate", headers=bob).json()["code"]
    client.delete(base, headers=alice)
    assert client.get(f"/certificates/{code}").status_code == 404


def test_certificate_refused_for_course_without_quizzes(client: TestClient, alice, bob) -> None:
    course = make_course(client, alice)
    base = f"/courses/{course['id']}"
    lesson = make_lesson(client, alice, course["id"])
    client.post(f"{base}/enroll", headers=bob)
    client.put(f"{base}/lessons/{lesson['id']}/complete", headers=bob)
    response = client.get(f"{base}/certificate", headers=bob)
    assert response.status_code == 409
    assert "quiz" in response.json()["detail"].lower()
