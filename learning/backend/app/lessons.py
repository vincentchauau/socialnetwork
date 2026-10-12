from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Course, Lesson
from app.schemas import (
    MAX_LESSONS_PER_COURSE,
    LessonIn,
    LessonOrderIn,
    LessonOut,
    LessonOutline,
    LessonPatch,
)
from app.services import (
    best_scores,
    completed_lesson_ids,
    find_enrollment,
    find_lesson,
    owned_course,
    passed_quiz_ids,
    quiz_brief,
    visible_course,
)
from sn_shared.deps import get_current_user
from sn_shared.security import TokenPayload

router = APIRouter()

FIRST_POSITION = 1
LOCKED = "Enrol in this course to view its lessons"


def _renumber(course: Course) -> None:
    for index, lesson in enumerate(course.lessons, start=FIRST_POSITION):
        lesson.position = index


def _lesson_out(db: Session, course: Course, lesson: Lesson, user: TokenPayload) -> LessonOut:
    quiz_ids = [lesson.quiz.id] if lesson.quiz is not None else []
    best = best_scores(db, quiz_ids, user.user_id)
    passed = passed_quiz_ids(db, quiz_ids, user.user_id)
    return LessonOut(
        id=lesson.id,
        course_id=course.id,
        title=lesson.title,
        content=lesson.content,
        video_url=lesson.video_url,
        position=lesson.position,
        completed=lesson.id in completed_lesson_ids(db, course, user.user_id),
        quiz=quiz_brief(lesson, best, passed),
    )


def _outline(db: Session, course: Course, user: TokenPayload) -> list[LessonOutline]:
    done = set(completed_lesson_ids(db, course, user.user_id))
    return [
        LessonOutline(
            id=lesson.id,
            title=lesson.title,
            position=lesson.position,
            has_quiz=lesson.quiz is not None,
            completed=lesson.id in done,
        )
        for lesson in course.lessons
    ]


@router.post(
    "/courses/{course_id}/lessons", status_code=status.HTTP_201_CREATED, response_model=LessonOut
)
def create_lesson(
    course_id: int,
    body: LessonIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonOut:
    course = owned_course(db, course_id, user)
    if len(course.lessons) >= MAX_LESSONS_PER_COURSE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lesson limit reached")
    lesson = Lesson(
        course_id=course.id,
        title=body.title,
        content=body.content,
        video_url=body.video_url,
        position=len(course.lessons) + FIRST_POSITION,
    )
    db.add(lesson)
    db.commit()
    db.expire_all()
    return _lesson_out(db, course, lesson, user)


@router.put("/courses/{course_id}/lessons/order", response_model=list[LessonOutline])
def reorder_lessons(
    course_id: int,
    body: LessonOrderIn,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LessonOutline]:
    course = owned_course(db, course_id, user)
    by_id = {lesson.id: lesson for lesson in course.lessons}
    if len(body.lesson_ids) != len(by_id) or set(body.lesson_ids) != set(by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Send every lesson id of the course exactly once"
        )
    for position, lesson_id in enumerate(body.lesson_ids, start=FIRST_POSITION):
        by_id[lesson_id].position = position
    db.commit()
    db.expire_all()
    return _outline(db, course, user)


@router.get("/courses/{course_id}/lessons/{lesson_id}", response_model=LessonOut)
def get_lesson(
    course_id: int,
    lesson_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonOut:
    course = visible_course(db, course_id, user)
    if course.owner_id != user.user_id and find_enrollment(db, course.id, user.user_id) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, LOCKED)
    return _lesson_out(db, course, find_lesson(course, lesson_id), user)


@router.patch("/courses/{course_id}/lessons/{lesson_id}", response_model=LessonOut)
def update_lesson(
    course_id: int,
    lesson_id: int,
    body: LessonPatch,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonOut:
    course = owned_course(db, course_id, user)
    lesson = find_lesson(course, lesson_id)
    # video_url may be explicitly nulled to remove the video; other fields ignore null.
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None or field == "video_url":
            setattr(lesson, field, value)
    db.commit()
    db.expire_all()
    return _lesson_out(db, course, lesson, user)


@router.delete(
    "/courses/{course_id}/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_lesson(
    course_id: int,
    lesson_id: int,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    course = owned_course(db, course_id, user)
    lesson = find_lesson(course, lesson_id)
    course.lessons.remove(lesson)
    db.flush()
    _renumber(course)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
