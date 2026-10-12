"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { apiFetch } from "@sn/api";
import { CourseForm } from "../CourseForm";
import {
  API,
  CourseDetail,
  RequireAuth,
  ResourceView,
  Shell,
  errorText,
  useAuth,
  useResource,
} from "../../lib";

export default function EditCoursePage() {
  const { id } = useParams<{ id: string }>();
  const auth = useAuth();
  const router = useRouter();
  const [state, reload] = useResource<CourseDetail>(
    auth.status === "signed-in" ? `/courses/${id}` : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function move(lessons: CourseDetail["lessons"], index: number, delta: -1 | 1) {
    const ids = lessons.map((lesson) => lesson.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    await run(() =>
      apiFetch(`${API}/courses/${id}/lessons/order`, {
        method: "PUT",
        body: JSON.stringify({ lesson_ids: ids }),
      }),
    );
  }

  async function removeLesson(lessonId: number, title: string) {
    if (!window.confirm(`Delete the lesson "${title}"? This cannot be undone.`)) return;
    await run(() => apiFetch(`${API}/courses/${id}/lessons/${lessonId}`, { method: "DELETE" }));
  }

  async function removeCourse() {
    if (!window.confirm("Delete this course and all its lessons and progress?")) return;
    await run(async () => {
      await apiFetch(`${API}/courses/${id}`, { method: "DELETE" });
      router.push("/author");
    });
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      reload();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Edit course">
      <RequireAuth auth={auth}>
        {() => (
          <ResourceView state={state}>
            {(course) => (
              <div className="stack">
                <p>
                  <Link href={`/courses/${course.id}`}>View course page</Link>
                </p>
                <CourseForm initial={course} onSaved={reload} />

                <h2>Lessons</h2>
                {error && (
                  <p role="alert" className="error">
                    {error}
                  </p>
                )}
                {course.lessons.length === 0 && <p className="muted">No lessons yet.</p>}
                <ol className="list" aria-label="Lessons">
                  {course.lessons.map((lesson, index) => (
                    <li key={lesson.id} className="card row wrap">
                      <Link href={`/author/${course.id}/lessons/${lesson.id}`}>
                        {lesson.position}. {lesson.title}
                      </Link>
                      {lesson.has_quiz && <span className="pill">quiz</span>}
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy || index === 0}
                        aria-label={`Move ${lesson.title} up`}
                        onClick={() => void move(course.lessons, index, -1)}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy || index === course.lessons.length - 1}
                        aria-label={`Move ${lesson.title} down`}
                        onClick={() => void move(course.lessons, index, 1)}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy}
                        aria-label={`Delete ${lesson.title}`}
                        onClick={() => void removeLesson(lesson.id, lesson.title)}
                      >
                        Delete
                      </button>
                    </li>
                  ))}
                </ol>
                <Link className="linkbtn" href={`/author/${course.id}/lessons/new`}>
                  Add a lesson
                </Link>
                <button type="button" className="secondary" disabled={busy} onClick={() => void removeCourse()}>
                  Delete course
                </button>
              </div>
            )}
          </ResourceView>
        )}
      </RequireAuth>
    </Shell>
  );
}
