from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Course, Enrollment, LessonCompletion, QuizAttempt
from app.schemas import CourseSummary, EnrollmentOut, ProgressOut
from app.services import (
    build_summaries,
    compute_progress,
    find_enrollment,
    find_lesson,
    require_enrollment,
    visible_course,
)
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()


def _published_course(db: Session, course_id: int, user: TokenPayload) -> Course:
    course = visible_course(db, course_id, user)
    if not course.published:
        # Owners can preview their draft, but nobody enrols in one.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return course


@router.post("/courses/{course_id}/enroll", response_model=EnrollmentOut)
def enroll(
    course_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnrollmentOut:
    course = _published_course(db, course_id, user)
    if course.owner_id == user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot enrol in your own course")
    enrollment = find_enrollment(db, course.id, user.user_id)
    if enrollment is None:
        enrollment = Enrollment(course_id=course.id, user_id=user.user_id, username=user.username)
        db.add(enrollment)
        try:
            db.commit()
        except IntegrityError:  # a concurrent request enrolled first
            db.rollback()
            enrollment = require_enrollment(db, course.id, user.user_id)
    return EnrollmentOut(course_id=course.id, enrolled_at=enrollment.enrolled_at)


@router.delete("/courses/{course_id}/enroll", status_code=status.HTTP_204_NO_CONTENT)
def unenroll(
    course_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    course = db.get(Course, course_id)
    enrollment = find_enrollment(db, course_id, user.user_id) if course else None
    if course is not None and enrollment is not None:
        lesson_ids = [lesson.id for lesson in course.lessons]
        quiz_ids = [lesson.quiz.id for lesson in course.lessons if lesson.quiz is not None]
        db.execute(
            delete(LessonCompletion).where(
                LessonCompletion.user_id == user.user_id, LessonCompletion.lesson_id.in_(lesson_ids)
            )
        )
        db.execute(
            delete(QuizAttempt).where(
                QuizAttempt.user_id == user.user_id, QuizAttempt.quiz_id.in_(quiz_ids)
            )
        )
        db.delete(enrollment)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/courses", response_model=list[CourseSummary])
def my_courses(
    user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CourseSummary]:
    courses = list(
        db.scalars(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == user.user_id, Course.published.is_(True))
            .order_by(Enrollment.enrolled_at.desc(), Enrollment.id.desc())
        )
    )
    return build_summaries(db, courses, user)


@router.get("/courses/{course_id}/progress", response_model=ProgressOut)
def get_progress(
    course_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressOut:
    course = visible_course(db, course_id, user)
    require_enrollment(db, course.id, user.user_id)
    return compute_progress(db, course, user.user_id)


def _set_completion(
    db: Session, course_id: int, lesson_id: int, user: TokenPayload, done: bool
) -> ProgressOut:
    course = visible_course(db, course_id, user)
    require_enrollment(db, course.id, user.user_id)
    lesson = find_lesson(course, lesson_id)
    existing = db.scalar(
        select(LessonCompletion).where(
            LessonCompletion.lesson_id == lesson.id, LessonCompletion.user_id == user.user_id
        )
    )
    if done and existing is None:
        db.add(LessonCompletion(lesson_id=lesson.id, user_id=user.user_id))
    elif not done and existing is not None:
        db.delete(existing)
    try:
        db.commit()
    except IntegrityError:  # a concurrent identical request already recorded it
        db.rollback()
    return compute_progress(db, course, user.user_id)


@router.put("/courses/{course_id}/lessons/{lesson_id}/complete", response_model=ProgressOut)
def complete_lesson(
    course_id: int,
    lesson_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressOut:
    return _set_completion(db, course_id, lesson_id, user, done=True)


@router.delete("/courses/{course_id}/lessons/{lesson_id}/complete", response_model=ProgressOut)
def uncomplete_lesson(
    course_id: int,
    lesson_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressOut:
    return _set_completion(db, course_id, lesson_id, user, done=False)
