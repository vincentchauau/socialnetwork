from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from app.schemas import StrictModel, Title

QUESTION_MAX = 500
OPTION_MAX = 200
EXPLANATION_MAX = 1000
MIN_OPTIONS = 2
MAX_OPTIONS = 6
MAX_QUESTIONS = 30
DEFAULT_PASS_PERCENT = 70
MIN_PASS_PERCENT = 1
MAX_PERCENT = 100


class OptionIn(StrictModel):
    text: Annotated[str, Field(min_length=1, max_length=OPTION_MAX)]
    is_correct: bool = False


class QuestionIn(StrictModel):
    text: Annotated[str, Field(min_length=1, max_length=QUESTION_MAX)]
    multiple: bool = False
    explanation: Annotated[str, Field(max_length=EXPLANATION_MAX)] = ""
    options: Annotated[list[OptionIn], Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)]

    @model_validator(mode="after")
    def _check_correct_options(self) -> "QuestionIn":
        correct = sum(option.is_correct for option in self.options)
        if correct == 0:
            raise ValueError("Mark at least one option as correct")
        if not self.multiple and correct != 1:
            raise ValueError("Single-choice questions need exactly one correct option")
        return self


class QuizIn(StrictModel):
    title: Title = "Quiz"
    pass_percent: Annotated[int, Field(ge=MIN_PASS_PERCENT, le=MAX_PERCENT)] = DEFAULT_PASS_PERCENT
    questions: Annotated[list[QuestionIn], Field(min_length=1, max_length=MAX_QUESTIONS)]


class OptionEditOut(BaseModel):
    id: int
    text: str
    is_correct: bool


class QuestionEditOut(BaseModel):
    id: int
    text: str
    multiple: bool
    explanation: str
    options: list[OptionEditOut]


class QuizEditOut(BaseModel):
    """Owner-only view: includes the answers."""

    id: int
    lesson_id: int
    title: str
    pass_percent: int
    questions: list[QuestionEditOut]


class OptionOut(BaseModel):
    id: int
    text: str


class QuestionOut(BaseModel):
    id: int
    text: str
    multiple: bool
    options: list[OptionOut]


class QuizOut(BaseModel):
    """Learner view: no correct answers and no explanations before submission."""

    id: int
    lesson_id: int
    title: str
    pass_percent: int
    best_score: int | None
    passed: bool
    questions: list[QuestionOut]


class AnswerIn(StrictModel):
    question_id: int
    option_ids: Annotated[list[int], Field(max_length=MAX_OPTIONS)]


class AttemptIn(StrictModel):
    answers: Annotated[list[AnswerIn], Field(max_length=MAX_QUESTIONS)]


class QuestionResult(BaseModel):
    question_id: int
    correct: bool
    explanation: str


class AttemptOut(BaseModel):
    attempt_id: int
    score_percent: int
    passed: bool
    pass_percent: int
    best_score: int
    best_passed: bool
    attempts_remaining: int
    # Per-question feedback is revealed only for a passing attempt.
    results: list[QuestionResult] | None = None
