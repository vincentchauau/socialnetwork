import os
from datetime import datetime, timedelta
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.grading import InvalidAnswers, grade, validate_answers
from app.models import Course, Lesson, Option, Question, Quiz, QuizAttempt, utcnow
from app.quiz_schemas import (
    AttemptIn,
    AttemptOut,
    OptionEditOut,
    OptionOut,
    QuestionEditOut,
    QuestionOut,
    QuizEditOut,
    QuizIn,
    QuizOut,
)
from app.services import (
    find_lesson,
    owned_course,
    require_enrollment,
    visible_course,
)
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

Clock = Callable[[], datetime]

FIRST_POSITION = 1
MAX_ATTEMPTS_ENV = "QUIZ_MAX_ATTEMPTS"
DEFAULT_MAX_ATTEMPTS = 5
ATTEMPT_WINDOW_HOURS = 24
QUIZ_NOT_FOUND = "Quiz not found"


def get_clock() -> Clock:
    """Injectable time source (overridden in tests)."""
    return utcnow


def max_attempts() -> int:
    try:
        return max(int(os.environ.get(MAX_ATTEMPTS_ENV, DEFAULT_MAX_ATTEMPTS)), 1)
    except ValueError:
        return DEFAULT_MAX_ATTEMPTS


def _recent_attempts(db: Session, quiz: Quiz, user_id: int, now: datetime) -> int:
    since = now - timedelta(hours=ATTEMPT_WINDOW_HOURS)
    return (
        db.scalar(
            select(func.count())
            .select_from(QuizAttempt)
            .where(
                QuizAttempt.quiz_id == quiz.id,
                QuizAttempt.user_id == user_id,
                QuizAttempt.created_at > since,
            )
        )
        or 0
    )


def _build_questions(body: QuizIn) -> list[Question]:
    return [
        Question(
            position=index,
            text=item.text,
            multiple=item.multiple,
            explanation=item.explanation,
            options=[
                Option(position=pos, text=option.text, is_correct=option.is_correct)
                for pos, option in enumerate(item.options, start=FIRST_POSITION)
            ],
        )
        for index, item in enumerate(body.questions, start=FIRST_POSITION)
    ]


def _edit_view(quiz: Quiz) -> QuizEditOut:
    return QuizEditOut(
        id=quiz.id,
        lesson_id=quiz.lesson_id,
        title=quiz.title,
        pass_percent=quiz.pass_percent,
        questions=[
            QuestionEditOut(
                id=q.id,
                text=q.text,
                multiple=q.multiple,
                explanation=q.explanation,
                options=[OptionEditOut(id=o.id, text=o.text, is_correct=o.is_correct) for o in q.options],
            )
            for q in quiz.questions
        ],
    )


def _best_and_passed(db: Session, quiz: Quiz, user_id: int) -> tuple[int | None, bool]:
    best = db.scalar(
        select(func.max(QuizAttempt.score_percent)).where(
            QuizAttempt.quiz_id == quiz.id, QuizAttempt.user_id == user_id
        )
    )
    passed = db.scalar(
        select(func.count())
        .select_from(QuizAttempt)
        .where(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.user_id == user_id,
            QuizAttempt.passed.is_(True),
        )
    )
    return best, bool(passed)


def _load_quiz(db: Session, quiz_id: int, user: TokenPayload) -> tuple[Quiz, Course]:
    """The quiz and its course; drafts of other users look like they do not exist."""
    quiz = db.get(Quiz, quiz_id)
    lesson = db.get(Lesson, quiz.lesson_id) if quiz else None
    if quiz is None or lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUIZ_NOT_FOUND)
    return quiz, visible_course(db, lesson.course_id, user)


@router.put("/courses/{course_id}/lessons/{lesson_id}/quiz", response_model=QuizEditOut)
def define_quiz(
    course_id: int,
    lesson_id: int,
    body: QuizIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizEditOut:
    course = owned_course(db, course_id, user)
    lesson = find_lesson(course, lesson_id)
    quiz = lesson.quiz
    if quiz is None:
        quiz = Quiz(lesson_id=lesson.id, title=body.title, pass_percent=body.pass_percent)
        db.add(quiz)
    else:
        # Old attempts were graded against questions that no longer exist.
        quiz.attempts.clear()
        quiz.questions.clear()
        db.flush()
        quiz.title, quiz.pass_percent = body.title, body.pass_percent
    quiz.questions.extend(_build_questions(body))
    db.commit()
    db.refresh(quiz)
    return _edit_view(quiz)


@router.delete(
    "/courses/{course_id}/lessons/{lesson_id}/quiz", status_code=status.HTTP_204_NO_CONTENT
)
def delete_quiz(
    course_id: int,
    lesson_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    lesson = find_lesson(owned_course(db, course_id, user), lesson_id)
    if lesson.quiz is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUIZ_NOT_FOUND)
    db.delete(lesson.quiz)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/quizzes/{quiz_id}/edit", response_model=QuizEditOut)
def get_quiz_for_owner(
    quiz_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizEditOut:
    quiz, course = _load_quiz(db, quiz_id, user)
    owned_course(db, course.id, user)
    return _edit_view(quiz)


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
def get_quiz(
    quiz_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizOut:
    quiz, course = _load_quiz(db, quiz_id, user)
    if course.owner_id != user.user_id:
        require_enrollment(db, course.id, user.user_id)
    best, passed = _best_and_passed(db, quiz, user.user_id)
    return QuizOut(
        id=quiz.id,
        lesson_id=quiz.lesson_id,
        title=quiz.title,
        pass_percent=quiz.pass_percent,
        best_score=best,
        passed=passed,
        questions=[
            QuestionOut(
                id=q.id,
                text=q.text,
                multiple=q.multiple,
                options=[OptionOut(id=o.id, text=o.text) for o in q.options],
            )
            for q in quiz.questions
        ],
    )


@router.post(
    "/quizzes/{quiz_id}/attempts", status_code=status.HTTP_201_CREATED, response_model=AttemptOut
)
def submit_attempt(
    quiz_id: int,
    body: AttemptIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> AttemptOut:
    quiz, course = _load_quiz(db, quiz_id, user)
    if course.owner_id == user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Course owners cannot take their own quiz")
    require_enrollment(db, course.id, user.user_id)
    now = clock()
    used = _recent_attempts(db, quiz, user.user_id, now)
    limit = max_attempts()
    if used >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Attempt limit reached ({limit} per {ATTEMPT_WINDOW_HOURS} hours). Try again later.",
        )
    try:
        chosen = validate_answers(quiz.questions, body.answers)
    except InvalidAnswers as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
    score, results = grade(quiz.questions, chosen)
    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.user_id,
        score_percent=score,
        passed=score >= quiz.pass_percent,
        created_at=now,
    )
    db.add(attempt)
    db.commit()
    best, passed = _best_and_passed(db, quiz, user.user_id)
    return AttemptOut(
        attempt_id=attempt.id,
        score_percent=score,
        passed=attempt.passed,
        pass_percent=quiz.pass_percent,
        best_score=best if best is not None else score,
        best_passed=passed,
        attempts_remaining=max(limit - used - 1, 0),
        # Feedback only on a pass, so failing attempts cannot be used to probe answers.
        results=results if attempt.passed else None,
    )
