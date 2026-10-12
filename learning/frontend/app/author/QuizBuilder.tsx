"use client";

import { FormEvent, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@sn/api";
import { API, errorText } from "../lib";

const MIN_OPTIONS = 2;
const MAX_OPTIONS = 6;
const MAX_QUESTIONS = 30;
const DEFAULT_PASS = 70;

interface OptionDraft {
  text: string;
  is_correct: boolean;
}

interface QuestionDraft {
  text: string;
  multiple: boolean;
  explanation: string;
  options: OptionDraft[];
}

interface QuizEdit {
  id: number;
  title: string;
  pass_percent: number;
  questions: QuestionDraft[];
}

const blankQuestion = (): QuestionDraft => ({
  text: "",
  multiple: false,
  explanation: "",
  options: [
    { text: "", is_correct: true },
    { text: "", is_correct: false },
  ],
});

function replaceAt<T>(items: T[], index: number, value: T): T[] {
  return items.map((item, i) => (i === index ? value : item));
}

function validate(questions: QuestionDraft[]): string | null {
  if (questions.length === 0) return "Add at least one question";
  for (const [index, question] of questions.entries()) {
    const label = `Question ${index + 1}`;
    if (!question.text.trim()) return `${label} needs text`;
    if (question.options.some((option) => !option.text.trim())) return `${label} has an empty option`;
    const correct = question.options.filter((option) => option.is_correct).length;
    if (correct === 0) return `${label} needs a correct option`;
    if (!question.multiple && correct !== 1) return `${label} is single choice: mark exactly one correct option`;
  }
  return null;
}

export function QuizBuilder({
  courseId,
  lessonId,
  quizId,
}: {
  courseId: string;
  lessonId: number;
  quizId: number | null;
}) {
  const base = `${API}/courses/${courseId}/lessons/${lessonId}/quiz`;
  const [exists, setExists] = useState(quizId !== null);
  const [title, setTitle] = useState("Quiz");
  const [pass, setPass] = useState(DEFAULT_PASS);
  const [questions, setQuestions] = useState<QuestionDraft[]>([]);
  const [loading, setLoading] = useState(quizId !== null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (quizId === null) return;
    apiFetch<QuizEdit>(`${API}/quizzes/${quizId}/edit`)
      .then((quiz) => {
        setTitle(quiz.title);
        setPass(quiz.pass_percent);
        // The server also sends ids, which the save endpoint rejects, so keep only the editable fields.
        setQuestions(
          quiz.questions.map((q) => ({
            text: q.text,
            multiple: q.multiple,
            explanation: q.explanation,
            options: q.options.map((o) => ({ text: o.text, is_correct: o.is_correct })),
          })),
        );
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load the quiz")))
      .finally(() => setLoading(false));
  }, [quizId]);

  const updateQuestion = (index: number, patch: Partial<QuestionDraft>) =>
    setQuestions((current) => replaceAt(current, index, { ...current[index], ...patch }));

  function updateOption(qIndex: number, oIndex: number, patch: Partial<OptionDraft>) {
    const question = questions[qIndex];
    let options = replaceAt(question.options, oIndex, { ...question.options[oIndex], ...patch });
    if (patch.is_correct && !question.multiple) {
      options = options.map((option, i) => ({ ...option, is_correct: i === oIndex }));
    }
    updateQuestion(qIndex, { options });
  }

  function setMultiple(index: number, multiple: boolean) {
    const question = questions[index];
    let options = question.options;
    if (!multiple) {
      const first = options.findIndex((option) => option.is_correct);
      options = options.map((option, i) => ({ ...option, is_correct: i === Math.max(first, 0) }));
    }
    updateQuestion(index, { multiple, options });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const problem = validate(questions);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(base, {
        method: "PUT",
        body: JSON.stringify({ title, pass_percent: pass, questions }),
      });
      setExists(true);
      setNotice("Quiz saved. Saving again resets learners' quiz attempts.");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm("Delete this quiz and all attempts?")) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(base, { method: "DELETE" });
      setExists(false);
      setQuestions([]);
      setNotice("Quiz deleted.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not delete the quiz");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="muted" role="status">Loading quiz…</p>;

  return (
    <form className="stack" onSubmit={save}>
      <label>
        Quiz title
        <input value={title} required maxLength={120} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Pass mark (%)
        <input
          type="number"
          min={1}
          max={100}
          value={pass}
          onChange={(e) => setPass(Number(e.target.value))}
        />
      </label>
      {questions.length === 0 && <p className="muted">No questions yet.</p>}
      {questions.map((question, qIndex) => (
        <fieldset key={qIndex} className="stack">
          <legend>Question {qIndex + 1}</legend>
          <label>
            Question text
            <input
              value={question.text}
              maxLength={500}
              onChange={(e) => updateQuestion(qIndex, { text: e.target.value })}
            />
          </label>
          <label className="inline">
            <input
              type="checkbox"
              checked={question.multiple}
              onChange={(e) => setMultiple(qIndex, e.target.checked)}
            />
            Multiple correct answers
          </label>
          {question.options.map((option, oIndex) => (
            <div className="row" key={oIndex}>
              <input
                type={question.multiple ? "checkbox" : "radio"}
                name={`correct-${qIndex}`}
                checked={option.is_correct}
                aria-label={`Option ${oIndex + 1} of question ${qIndex + 1} is correct`}
                style={{ width: "auto" }}
                onChange={(e) => updateOption(qIndex, oIndex, { is_correct: e.target.checked })}
              />
              <input
                value={option.text}
                maxLength={200}
                aria-label={`Option ${oIndex + 1} text`}
                onChange={(e) => updateOption(qIndex, oIndex, { text: e.target.value })}
              />
              <button
                type="button"
                className="secondary"
                disabled={question.options.length <= MIN_OPTIONS}
                aria-label={`Remove option ${oIndex + 1} of question ${qIndex + 1}`}
                onClick={() =>
                  updateQuestion(qIndex, { options: question.options.filter((_, i) => i !== oIndex) })
                }
              >
                ✕
              </button>
            </div>
          ))}
          <div className="row wrap">
            <button
              type="button"
              className="secondary"
              disabled={question.options.length >= MAX_OPTIONS}
              onClick={() =>
                updateQuestion(qIndex, {
                  options: [...question.options, { text: "", is_correct: false }],
                })
              }
            >
              Add option
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setQuestions(questions.filter((_, i) => i !== qIndex))}
            >
              Remove question
            </button>
          </div>
          <label>
            Explanation (shown after submitting)
            <textarea
              value={question.explanation}
              maxLength={1000}
              rows={2}
              onChange={(e) => updateQuestion(qIndex, { explanation: e.target.value })}
            />
          </label>
        </fieldset>
      ))}
      <button
        type="button"
        className="secondary"
        disabled={questions.length >= MAX_QUESTIONS}
        onClick={() => setQuestions([...questions, blankQuestion()])}
      >
        Add question
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="ok">
          {notice}
        </p>
      )}
      <div className="row wrap">
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save quiz"}
        </button>
        {exists && (
          <button type="button" className="secondary" disabled={busy} onClick={() => void remove()}>
            Delete quiz
          </button>
        )}
      </div>
    </form>
  );
}
