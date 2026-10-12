"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

import { ApiError, User, apiFetch, loadSession } from "@sn/api";

export const API = "/api/learning";
export const LEVELS = ["beginner", "intermediate", "advanced"] as const;
export type Level = (typeof LEVELS)[number];

export interface CourseSummary {
  id: number;
  title: string;
  summary: string;
  level: Level;
  tags: string[];
  published: boolean;
  owner_username: string;
  is_owner: boolean;
  lesson_count: number;
  enrolment_count: number;
  enrolled: boolean;
  progress_percent: number;
  created_at: string;
}

export interface LessonOutline {
  id: number;
  title: string;
  position: number;
  has_quiz: boolean;
  completed: boolean;
}

export interface CourseDetail extends CourseSummary {
  lessons: LessonOutline[];
}

export interface QuizBrief {
  id: number;
  title: string;
  pass_percent: number;
  question_count: number;
  best_score: number | null;
  passed: boolean;
}

export interface Lesson {
  id: number;
  course_id: number;
  title: string;
  content: string;
  video_url: string | null;
  position: number;
  completed: boolean;
  quiz: QuizBrief | null;
}

export interface Progress {
  course_id: number;
  total_lessons: number;
  completed_lesson_ids: number[];
  percent: number;
  quizzes_total: number;
  quizzes_passed: number;
  completed: boolean;
}

export function errorText(error: unknown, fallback = "Something went wrong"): string {
  return error instanceof ApiError || error instanceof Error ? error.message : fallback;
}

export type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

export function useAuth(): Auth {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });
  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);
  return auth;
}

export type Loaded<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

/** Fetches `path` (null = skip) and exposes loading / error / data plus a reload. */
export function useResource<T>(path: string | null): [Loaded<T>, () => void, (data: T) => void] {
  const [state, setState] = useState<Loaded<T>>({ status: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setState((current) => (current.status === "ready" ? current : { status: "loading" }));
    apiFetch<T>(`${API}${path}`)
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch((error: unknown) => {
        if (!cancelled) setState({ status: "error", message: errorText(error, "Could not load") });
      });
    return () => {
      cancelled = true;
    };
  }, [path, tick]);
  return [state, () => setTick((value) => value + 1), (data) => setState({ status: "ready", data })];
}

export function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="stack">
      <div className="topbar">
        <a href="/">← Home</a>
        <nav className="nav" aria-label="Learning">
          <Link href="/">Courses</Link>
          <Link href="/my">My learning</Link>
          <Link href="/author">Teach</Link>
        </nav>
      </div>
      <h1>{title}</h1>
      {children}
    </div>
  );
}

/** Renders loading/error/anonymous states; children only when signed in. */
export function RequireAuth({
  auth,
  children,
}: {
  auth: Auth;
  children: (user: User) => ReactNode;
}) {
  if (auth.status === "loading") return <p className="muted" role="status">Loading…</p>;
  if (auth.status === "error") {
    return <p role="alert" className="error">Could not reach the server. Please try again.</p>;
  }
  if (auth.status === "anonymous") {
    return (
      <p>
        Please <a href="/login">sign in</a> to continue.
      </p>
    );
  }
  return <>{children(auth.user)}</>;
}

export function ResourceView<T>({
  state,
  children,
}: {
  state: Loaded<T>;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") return <p className="muted" role="status">Loading…</p>;
  if (state.status === "error") return <p role="alert" className="error">{state.message}</p>;
  return <>{children(state.data)}</>;
}

export function ProgressBar({ percent, label }: { percent: number; label: string }) {
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <span style={{ width: `${percent}%` }} />
    </div>
  );
}

export function CourseCard({ course }: { course: CourseSummary }) {
  return (
    <li className="card stack">
      <h2>
        <Link href={`/courses/${course.id}`}>{course.title}</Link>
      </h2>
      {course.summary && <p className="prewrap">{course.summary}</p>}
      <div className="wrap">
        <span className="pill">{course.level}</span>
        {!course.published && <span className="pill">draft</span>}
        {course.tags.map((tag) => (
          <span className="pill" key={tag}>
            {tag}
          </span>
        ))}
      </div>
      <p className="muted">
        By {course.owner_username} · {course.lesson_count} lessons · {course.enrolment_count} enrolled
      </p>
      {course.enrolled && (
        <ProgressBar percent={course.progress_percent} label={`Progress in ${course.title}`} />
      )}
    </li>
  );
}
