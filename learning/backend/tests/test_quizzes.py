import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_course, make_lesson, make_quiz, quiz_body


@pytest.fixture
def setup(client: TestClient, alice, bob):
    course = make_course(client, alice)
    lesson = make_lesson(client, alice, course["id"])
    quiz = make_quiz(client, alice, course["id"], lesson["id"])
    client.post(f"/courses/{course['id']}/enroll", headers=bob)
    return {"course": course, "lesson": lesson, "quiz": quiz}


def _answers(quiz: dict, picks: list[list[str]]) -> dict:
    """Pick options by text for each question (in order)."""
    answers = []
    for question, texts in zip(quiz["questions"], picks):
        ids = [o["id"] for o in question["options"] if o["text"] in texts]
        answers.append({"question_id": question["id"], "option_ids": ids})
    return {"answers": answers}


def test_define_quiz_owner_only(client: TestClient, alice, bob, setup) -> None:
    url = f"/courses/{setup['course']['id']}/lessons/{setup['lesson']['id']}/quiz"
    assert client.put(url, json=quiz_body()).status_code == 401
    assert client.put(url, json=quiz_body(), headers=bob).status_code == 403
    assert client.delete(url, headers=bob).status_code == 403
    assert client.delete(url).status_code == 401


def test_owner_edit_view_has_answers(client: TestClient, alice, bob, setup) -> None:
    url = f"/quizzes/{setup['quiz']['id']}/edit"
    owner = client.get(url, headers=alice).json()
    assert owner["questions"][0]["options"][1]["is_correct"] is True
    assert client.get(url, headers=bob).status_code == 403
    assert client.get(url).status_code == 401


def test_learner_view_hides_answers(client: TestClient, bob, setup) -> None:
    response = client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob)
    assert response.status_code == 200
    text = response.text
    assert "is_correct" not in text
    assert "explanation" not in text
    assert "Basic maths" not in text
    body = response.json()
    assert body["best_score"] is None
    assert body["questions"][1]["multiple"] is True


def test_lesson_detail_exposes_quiz_brief_without_answers(client: TestClient, bob, setup) -> None:
    url = f"/courses/{setup['course']['id']}/lessons/{setup['lesson']['id']}"
    body = client.get(url, headers=bob).json()
    assert body["quiz"]["question_count"] == 2
    assert body["quiz"]["id"] == setup["quiz"]["id"]
    assert "is_correct" not in client.get(url, headers=bob).text


def test_learner_view_requires_enrolment(client: TestClient, setup) -> None:
    from tests.conftest import auth_cookie

    carol = auth_cookie(3, "carol")
    quiz_id = setup["quiz"]["id"]
    assert client.get(f"/quizzes/{quiz_id}").status_code == 401
    assert client.get(f"/quizzes/{quiz_id}", headers=carol).status_code == 403
    assert client.post(f"/quizzes/{quiz_id}/attempts", json={"answers": []}, headers=carol).status_code == 403
    assert client.get("/quizzes/999", headers=carol).status_code == 404


def test_draft_quiz_hidden(client: TestClient, alice, bob, setup) -> None:
    client.patch(f"/courses/{setup['course']['id']}", json={"published": False}, headers=alice)
    assert client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).status_code == 404


def test_attempt_all_correct(client: TestClient, bob, setup) -> None:
    quiz = client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).json()
    body = _answers(quiz, [["4"], ["2", "3"]])
    result = client.post(f"/quizzes/{quiz['id']}/attempts", json=body, headers=bob).json()
    assert result["score_percent"] == 100
    assert result["passed"] is True
    assert result["best_score"] == 100
    assert all(r["correct"] for r in result["results"])
    assert result["results"][0]["explanation"] == "Basic maths"


def test_attempt_partial_and_best_kept(client: TestClient, bob, setup) -> None:
    quiz = client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).json()
    url = f"/quizzes/{quiz['id']}/attempts"
    wrong_multi = client.post(url, json=_answers(quiz, [["4"], ["2"]]), headers=bob).json()
    assert wrong_multi["score_percent"] == 50
    assert wrong_multi["passed"] is False
    assert [r["correct"] for r in wrong_multi["results"]] == [True, False]
    best = client.post(url, json=_answers(quiz, [["4"], ["2", "3"]]), headers=bob).json()
    worse = client.post(url, json=_answers(quiz, [["3"], ["4"]]), headers=bob).json()
    assert worse["score_percent"] == 0
    assert worse["best_score"] == 100
    assert worse["best_passed"] is True
    seen = client.get(f"/quizzes/{quiz['id']}", headers=bob).json()
    assert seen["best_score"] == 100
    assert seen["passed"] is True
    assert best["attempt_id"] != worse["attempt_id"]


def test_attempt_unanswered_counts_wrong(client: TestClient, bob, setup) -> None:
    quiz_id = setup["quiz"]["id"]
    result = client.post(f"/quizzes/{quiz_id}/attempts", json={"answers": []}, headers=bob).json()
    assert result["score_percent"] == 0
    assert len(result["results"]) == 2


def test_attempt_validation(client: TestClient, bob, setup) -> None:
    quiz = client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).json()
    url = f"/quizzes/{quiz['id']}/attempts"
    q1, q2 = quiz["questions"]
    opt1 = q1["options"][0]["id"]
    opt2 = q1["options"][1]["id"]
    bad_bodies = [
        {"answers": [{"question_id": 9999, "option_ids": [opt1]}]},
        {"answers": [{"question_id": q1["id"], "option_ids": [opt1, opt2]}]},  # single choice
        {"answers": [{"question_id": q1["id"], "option_ids": [q2["options"][0]["id"]]}]},
        {"answers": [{"question_id": q1["id"], "option_ids": [opt1, opt1]}]},
        {"answers": [{"question_id": q1["id"], "option_ids": [opt1]}] * 2},
        {"answers": [{"question_id": q1["id"], "option_ids": list(range(7))}]},
        {"answers": "nope"},
    ]
    for body in bad_bodies:
        assert client.post(url, json=body, headers=bob).status_code == 422, body
    assert client.post(url, json={"answers": []}).status_code == 401


def test_owner_cannot_attempt_unenrolled(client: TestClient, alice, setup) -> None:
    url = f"/quizzes/{setup['quiz']['id']}/attempts"
    assert client.post(url, json={"answers": []}, headers=alice).status_code == 403


def test_custom_pass_mark(client: TestClient, alice, bob, setup) -> None:
    course_id, lesson_id = setup["course"]["id"], setup["lesson"]["id"]
    quiz = make_quiz(client, alice, course_id, lesson_id, pass_percent=50)
    learner = client.get(f"/quizzes/{quiz['id']}", headers=bob).json()
    result = client.post(
        f"/quizzes/{quiz['id']}/attempts", json=_answers(learner, [["4"], ["2"]]), headers=bob
    ).json()
    assert result["score_percent"] == 50
    assert result["passed"] is True
    assert result["pass_percent"] == 50


def test_redefining_quiz_resets_attempts(client: TestClient, alice, bob, setup) -> None:
    quiz = client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).json()
    client.post(f"/quizzes/{quiz['id']}/attempts", json=_answers(quiz, [["4"], ["2", "3"]]), headers=bob)
    redefined = make_quiz(client, alice, setup["course"]["id"], setup["lesson"]["id"])
    assert redefined["id"] == quiz["id"]
    assert client.get(f"/quizzes/{quiz['id']}", headers=bob).json()["best_score"] is None


def test_delete_quiz(client: TestClient, alice, bob, setup) -> None:
    url = f"/courses/{setup['course']['id']}/lessons/{setup['lesson']['id']}/quiz"
    assert client.delete(url, headers=alice).status_code == 204
    assert client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).status_code == 404
    assert client.delete(url, headers=alice).status_code == 404


def test_deleting_lesson_removes_quiz(client: TestClient, alice, bob, setup) -> None:
    client.delete(f"/courses/{setup['course']['id']}/lessons/{setup['lesson']['id']}", headers=alice)
    assert client.get(f"/quizzes/{setup['quiz']['id']}", headers=bob).status_code == 404


@pytest.mark.parametrize(
    "mutation",
    [
        {"pass_percent": 0},
        {"pass_percent": 101},
        {"questions": []},
        {"questions": [{"text": "q", "multiple": False, "options": [{"text": "a", "is_correct": True}]}]},
        {"questions": [{"text": "q", "options": [{"text": str(i), "is_correct": i == 0} for i in range(7)]}]},
        {"questions": [{"text": "q", "options": [{"text": "a", "is_correct": False}, {"text": "b", "is_correct": False}]}]},
        {"questions": [{"text": "q", "multiple": False, "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}]}]},
        {"questions": [{"text": "", "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}]}]},
        {"questions": [{"text": "q", "explanation": "e" * 1001, "options": [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": False}]}]},
        {"questions": [{"text": "q", "options": [{"text": "", "is_correct": True}, {"text": "b", "is_correct": False}]}]},
    ],
)
def test_quiz_validation(client: TestClient, alice, setup, mutation) -> None:
    url = f"/courses/{setup['course']['id']}/lessons/{setup['lesson']['id']}/quiz"
    response = client.put(url, json=quiz_body(**mutation), headers=alice)
    assert response.status_code == 422


def test_quiz_too_many_questions(client: TestClient, alice, setup) -> None:
    question = quiz_body()["questions"][0]
    url = f"/courses/{setup['course']['id']}/lessons/{setup['lesson']['id']}/quiz"
    assert client.put(url, json=quiz_body(questions=[question] * 31), headers=alice).status_code == 422
