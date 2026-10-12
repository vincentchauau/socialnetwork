"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, RequireAuth, ResourceView, Shell, errorText, useAuth, useResource } from "../../lib";

interface Question {
  id: number;
  text: string;
  multiple: boolean;
  options: { id: number; text: string }[];
}

interface Quiz {
  id: number;
  title: string;
  pass_percent: number;
  best_score: number | null;
  passed: boolean;
  questions: Question[];
}

interface Result {
  score_percent: number;
  passed: boolean;
  pass_percent: number;
  best_score: number;
  results: { question_id: number; correct: boolean; explanation: string }[];
}

type Picks = Record<number, number[]>;

function togglePick(picks: Picks, question: Question, optionId: number): Picks {
  const current = picks[question.id] ?? [];
  if (!question.multiple) return { ...picks, [question.id]: [optionId] };
  const next = current.includes(optionId)
    ? current.filter((value) => value !== optionId)
    : [...current, optionId];
  return { ...picks, [question.id]: next };
}

function QuizForm({ quiz, courseId }: { quiz: Quiz; courseId: string | null }) {
  const [picks, setPicks] = useState<Picks>({});
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const answers = quiz.questions.map((question) => ({
      question_id: question.id,
      option_ids: picks[question.id] ?? [],
    }));
    try {
      setResult(
        await apiFetch<Result>(`${API}/quizzes/${quiz.id}/attempts`, {
          method: "POST",
          body: JSON.stringify({ answers }),
        }),
      );
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  function retry() {
    setResult(null);
    setPicks({});
  }

  if (result) {
    const byQuestion = new Map(result.results.map((item) => [item.question_id, item]));
    return (
      <div className="stack">
        <p role="status" className={result.passed ? "ok" : "error"}>
          You scored {result.score_percent}% — {result.passed ? "passed" : "not passed"} (pass mark{" "}
          {result.pass_percent}%). Best score: {result.best_score}%.
        </p>
        <ol className="list">
          {quiz.questions.map((question) => {
            const item = byQuestion.get(question.id);
            return (
              <li key={question.id} className="card stack">
                <h3>{question.text}</h3>
                <p className={item?.correct ? "ok" : "error"}>{item?.correct ? "Correct" : "Incorrect"}</p>
                {item?.explanation && <p className="prewrap muted">{item.explanation}</p>}
              </li>
            );
          })}
        </ol>
        <div className="row wrap">
          <button type="button" onClick={retry}>
            Try again
          </button>
          {courseId && (
            <Link className="linkbtn secondary" href={`/courses/${courseId}`}>
              Back to course
            </Link>
          )}
        </div>
      </div>
    );
  }

  return (
    <form className="stack" onSubmit={submit}>
      <p className="muted">
        Pass mark {quiz.pass_percent}%.
        {quiz.best_score !== null && ` Your best score: ${quiz.best_score}%.`}
      </p>
      {quiz.questions.map((question, index) => (
        <fieldset key={question.id}>
          <legend>
            {index + 1}. {question.text}
          </legend>
          <p className="muted">{question.multiple ? "Choose all that apply" : "Choose one"}</p>
          <div className="stack">
            {question.options.map((option) => (
              <label key={option.id} className="inline">
                <input
                  type={question.multiple ? "checkbox" : "radio"}
                  name={`question-${question.id}`}
                  checked={(picks[question.id] ?? []).includes(option.id)}
                  onChange={() => setPicks(togglePick(picks, question, option.id))}
                />
                {option.text}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy}>
        {busy ? "Submitting…" : "Submit answers"}
      </button>
    </form>
  );
}

function QuizPageContent() {
  const { id } = useParams<{ id: string }>();
  const courseId = useSearchParams().get("course");
  const auth = useAuth();
  const [state] = useResource<Quiz>(auth.status === "signed-in" ? `/quizzes/${id}` : null);
  return (
    <Shell title="Quiz">
      <RequireAuth auth={auth}>
        {() => (
          <ResourceView state={state}>
            {(quiz) => (
              <div className="stack">
                <h2>{quiz.title}</h2>
                <QuizForm quiz={quiz} courseId={courseId} />
              </div>
            )}
          </ResourceView>
        )}
      </RequireAuth>
    </Shell>
  );
}

export default function QuizPage() {
  return (
    <Suspense fallback={<p className="muted">Loading…</p>}>
      <QuizPageContent />
    </Suspense>
  );
}
