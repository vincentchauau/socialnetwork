"""Access rules and read-model builders shared by the routers."""

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Course, Enrollment, Lesson, LessonCompletion, QuizAttempt
from app.schemas import (
    CourseDetail,
    CourseSummary,
    LessonOutline,
    ProgressOut,
    QuizBrief,
)
from sn_shared.security import AuthError, TokenPayload, payload_from_cookies

FULL_PERCENT = 100

NOT_FOUND_COURSE = "Course not found"
NOT_FOUND_LESSON = "Lesson not found"
NOT_OWNER = "Only the course owner can do this"
NOT_ENROLLED = "Enrol in this course first"


def optional_user(request: Request) -> TokenPayload | None:
    """The signed-in user, or None for anonymous (or invalid-cookie) visitors."""
    try:
        return payload_from_cookies(request.cookies)
    except AuthError:
        return None


def percent_of(done: int, total: int) -> int:
    return done * FULL_PERCENT // total if total else 0


def visible_course(db: Session, course_id: int, user: TokenPayload | None) -> Course:
    """A course the caller may see: published, or their own draft. Others get 404."""
    course = db.get(Course, course_id)
    is_owner = user is not None and course is not None and course.owner_id == user.user_id
    if course is None or not (course.published or is_owner):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_COURSE)
    return course


def owned_course(db: Session, course_id: int, user: TokenPayload) -> Course:
    course = visible_course(db, course_id, user)
    if course.owner_id != user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_OWNER)
    return course


def find_enrollment(db: Session, course_id: int, user_id: int) -> Enrollment | None:
    return db.scalar(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user_id)
    )


def require_enrollment(db: Session, course_id: int, user_id: int) -> Enrollment:
    enrollment = find_enrollment(db, course_id, user_id)
    if enrollment is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_ENROLLED)
    return enrollment


def find_lesson(course: Course, lesson_id: int) -> Lesson:
    for lesson in course.lessons:
        if lesson.id == lesson_id:
            return lesson
    raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_LESSON)


def completed_lesson_ids(db: Session, course: Course, user_id: int) -> list[int]:
    lesson_ids = [lesson.id for lesson in course.lessons]
    if not lesson_ids:
        return []
    rows = db.scalars(
        select(LessonCompletion.lesson_id).where(
            LessonCompletion.user_id == user_id, LessonCompletion.lesson_id.in_(lesson_ids)
        )
    )
    return sorted(rows)


def best_scores(db: Session, quiz_ids: list[int], user_id: int) -> dict[int, int]:
    if not quiz_ids:
        return {}
    rows = db.execute(
        select(QuizAttempt.quiz_id, func.max(QuizAttempt.score_percent))
        .where(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id.in_(quiz_ids))
        .group_by(QuizAttempt.quiz_id)
    ).all()
    return {quiz_id: score for quiz_id, score in rows}


def passed_quiz_ids(db: Session, quiz_ids: list[int], user_id: int) -> set[int]:
    if not quiz_ids:
        return set()
    rows = db.scalars(
        select(QuizAttempt.quiz_id)
        .where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.quiz_id.in_(quiz_ids),
            QuizAttempt.passed.is_(True),
        )
        .distinct()
    )
    return set(rows)


def quiz_brief(lesson: Lesson, best: dict[int, int], passed: set[int]) -> QuizBrief | None:
    quiz = lesson.quiz
    if quiz is None:
        return None
    return QuizBrief(
        id=quiz.id,
        title=quiz.title,
        pass_percent=quiz.pass_percent,
        question_count=len(quiz.questions),
        best_score=best.get(quiz.id),
        passed=quiz.id in passed,
    )


def compute_progress(db: Session, course: Course, user_id: int) -> ProgressOut:
    done = completed_lesson_ids(db, course, user_id)
    quiz_ids = [lesson.quiz.id for lesson in course.lessons if lesson.quiz is not None]
    passed = passed_quiz_ids(db, quiz_ids, user_id)
    total = len(course.lessons)
    return ProgressOut(
        course_id=course.id,
        total_lessons=total,
        completed_lesson_ids=done,
        percent=percent_of(len(done), total),
        quizzes_total=len(quiz_ids),
        quizzes_passed=len(passed),
        completed=total > 0 and len(done) == total and len(passed) == len(quiz_ids),
    )


def _group_counts(db: Session, stmt) -> dict[int, int]:
    return {key: count for key, count in db.execute(stmt).all()}


def build_summaries(
    db: Session, courses: list[Course], user: TokenPayload | None
) -> list[CourseSummary]:
    ids = [course.id for course in courses]
    if not ids:
        return []
    enrolment_counts = _group_counts(
        db,
        select(Enrollment.course_id, func.count())
        .where(Enrollment.course_id.in_(ids))
        .group_by(Enrollment.course_id),
    )
    enrolled_in: set[int] = set()
    done_counts: dict[int, int] = {}
    if user is not None:
        enrolled_in = set(
            db.scalars(
                select(Enrollment.course_id).where(
                    Enrollment.course_id.in_(ids), Enrollment.user_id == user.user_id
                )
            )
        )
        done_counts = _group_counts(
            db,
            select(Lesson.course_id, func.count())
            .join(LessonCompletion, LessonCompletion.lesson_id == Lesson.id)
            .where(Lesson.course_id.in_(ids), LessonCompletion.user_id == user.user_id)
            .group_by(Lesson.course_id),
        )
    return [
        CourseSummary(
            id=course.id,
            title=course.title,
            summary=course.summary,
            level=course.level,  # type: ignore[arg-type]
            tags=[tag.tag for tag in course.tags],
            published=course.published,
            owner_username=course.owner_username,
            is_owner=user is not None and course.owner_id == user.user_id,
            lesson_count=len(course.lessons),
            enrolment_count=enrolment_counts.get(course.id, 0),
            enrolled=course.id in enrolled_in,
            progress_percent=percent_of(done_counts.get(course.id, 0), len(course.lessons)),
            created_at=course.created_at,
        )
        for course in courses
    ]


def build_detail(db: Session, course: Course, user: TokenPayload | None) -> CourseDetail:
    summary = build_summaries(db, [course], user)[0]
    done = set(completed_lesson_ids(db, course, user.user_id)) if user is not None else set()
    outline = [
        LessonOutline(
            id=lesson.id,
            title=lesson.title,
            position=lesson.position,
            has_quiz=lesson.quiz is not None,
            completed=lesson.id in done,
        )
        for lesson in course.lessons
    ]
    return CourseDetail(**summary.model_dump(), lessons=outline)
