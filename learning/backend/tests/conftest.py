import os
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

# create_app() runs at import time and needs these.
os.environ.setdefault("JWT_SECRET", "t" * 40)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.main import create_app  # noqa: E402
from sn_shared import COOKIE_NAME, create_token  # noqa: E402


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "t" * 40)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app("sqlite://")) as test_client:
        yield test_client


def auth_cookie(user_id: int = 1, username: str = "alice") -> dict[str, str]:
    return {"Cookie": f"{COOKIE_NAME}={create_token(user_id, username)}"}


@pytest.fixture
def alice() -> dict[str, str]:
    return auth_cookie(1, "alice")


@pytest.fixture
def bob() -> dict[str, str]:
    return auth_cookie(2, "bob")


def make_course(client: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body = {"title": "Python 101", "summary": "Basics", "published": True, **overrides}
    response = client.post("/courses", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def make_lesson(
    client: TestClient, headers: dict[str, str], course_id: int, **overrides: Any
) -> dict[str, Any]:
    body = {"title": "Intro", "content": "Hello **world**", **overrides}
    response = client.post(f"/courses/{course_id}/lessons", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def quiz_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "title": "Check",
        "pass_percent": 70,
        "questions": [
            {
                "text": "2+2?",
                "multiple": False,
                "explanation": "Basic maths",
                "options": [
                    {"text": "3", "is_correct": False},
                    {"text": "4", "is_correct": True},
                ],
            },
            {
                "text": "Primes?",
                "multiple": True,
                "explanation": "2 and 3 are prime",
                "options": [
                    {"text": "2", "is_correct": True},
                    {"text": "3", "is_correct": True},
                    {"text": "4", "is_correct": False},
                ],
            },
        ],
    }
    return {**body, **overrides}


def make_quiz(
    client: TestClient, headers: dict[str, str], course_id: int, lesson_id: int, **overrides: Any
) -> dict[str, Any]:
    response = client.put(
        f"/courses/{course_id}/lessons/{lesson_id}/quiz", json=quiz_body(**overrides), headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()
