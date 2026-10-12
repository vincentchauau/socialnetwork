"""Pure quiz grading and answer validation."""

from app.models import Question
from app.quiz_schemas import AnswerIn, QuestionResult
from app.services import FULL_PERCENT


class InvalidAnswers(ValueError):
    pass


def validate_answers(questions: list[Question], answers: list[AnswerIn]) -> dict[int, set[int]]:
    """Map question id -> chosen option ids, or raise InvalidAnswers."""
    by_id = {question.id: question for question in questions}
    chosen: dict[int, set[int]] = {}
    for answer in answers:
        question = by_id.get(answer.question_id)
        if question is None:
            raise InvalidAnswers("Answer refers to a question that is not in this quiz")
        if answer.question_id in chosen:
            raise InvalidAnswers("Each question can be answered only once")
        picked = set(answer.option_ids)
        if len(picked) != len(answer.option_ids):
            raise InvalidAnswers("Duplicate option in answer")
        if not picked <= {option.id for option in question.options}:
            raise InvalidAnswers("Answer refers to an option that is not part of the question")
        if len(picked) > 1 and not question.multiple:
            raise InvalidAnswers("Only one option can be chosen for a single-choice question")
        chosen[answer.question_id] = picked
    return chosen


def grade(
    questions: list[Question], chosen: dict[int, set[int]]
) -> tuple[int, list[QuestionResult]]:
    """Score as a whole percent plus per-question results. Unanswered counts as wrong."""
    results = []
    for question in questions:
        correct_ids = {option.id for option in question.options if option.is_correct}
        is_correct = chosen.get(question.id, set()) == correct_ids
        results.append(
            QuestionResult(
                question_id=question.id, correct=is_correct, explanation=question.explanation
            )
        )
    right = sum(result.correct for result in results)
    return right * FULL_PERCENT // len(questions), results
