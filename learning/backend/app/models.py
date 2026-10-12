from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ALL_DELETE = "all, delete-orphan"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (Index("ix_courses_published_id", "published", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    owner_username: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(1000), default="")
    level: Mapped[str] = mapped_column(String(16))
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tags: Mapped[list["CourseTag"]] = relationship(
        cascade=ALL_DELETE, order_by="CourseTag.tag", lazy="selectin"
    )
    lessons: Mapped[list["Lesson"]] = relationship(
        cascade=ALL_DELETE, order_by="Lesson.position", lazy="selectin"
    )
    enrollments: Mapped[list["Enrollment"]] = relationship(cascade=ALL_DELETE)


class CourseTag(Base):
    __tablename__ = "course_tags"
    __table_args__ = (UniqueConstraint("course_id", "tag"), Index("ix_course_tags_tag", "tag"))

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    tag: Mapped[str] = mapped_column(String(30))


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text, default="")
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(Integer)

    quiz: Mapped["Quiz | None"] = relationship(cascade=ALL_DELETE, uselist=False, lazy="selectin")
    completions: Mapped[list["LessonCompletion"]] = relationship(cascade=ALL_DELETE)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    username: Mapped[str] = mapped_column(String(32))
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    certificate_code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonCompletion(Base):
    __tablename__ = "lesson_completions"
    __table_args__ = (UniqueConstraint("lesson_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    pass_percent: Mapped[int] = mapped_column(Integer)

    questions: Mapped[list["Question"]] = relationship(
        cascade=ALL_DELETE, order_by="Question.position", lazy="selectin"
    )
    attempts: Mapped[list["QuizAttempt"]] = relationship(cascade=ALL_DELETE)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(500))
    multiple: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation: Mapped[str] = mapped_column(String(1000), default="")

    options: Mapped[list["Option"]] = relationship(
        cascade=ALL_DELETE, order_by="Option.position", lazy="selectin"
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(200))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (Index("ix_attempts_quiz_user", "quiz_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    user_id: Mapped[int] = mapped_column(Integer)
    score_percent: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
