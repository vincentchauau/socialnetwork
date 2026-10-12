"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { apiFetch } from "@sn/api";
import {
  API,
  Lesson,
  RequireAuth,
  ResourceView,
  Shell,
  errorText,
  useAuth,
  useResource,
} from "../../../../lib";

function isHttps(url: string): boolean {
  return url.startsWith("https://");
}

export default function LessonPage() {
  const { id, lessonId } = useParams<{ id: string; lessonId: string }>();
  const auth = useAuth();
  const signedIn = auth.status === "signed-in";
  const [state, reload] = useResource<Lesson>(signedIn ? `/courses/${id}/lessons/${lessonId}` : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setCompleted(done: boolean) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`${API}/courses/${id}/lessons/${lessonId}/complete`, {
        method: done ? "PUT" : "DELETE",
      });
      reload();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Lesson">
      <p>
        <Link href={`/courses/${id}`}>← Back to course</Link>
      </p>
      <RequireAuth auth={auth}>
        {() => (
          <ResourceView state={state}>
            {(lesson) => (
              <article className="stack">
                <h2>{lesson.title}</h2>
                {lesson.video_url && isHttps(lesson.video_url) && (
                  <p>
                    <a href={lesson.video_url} target="_blank" rel="noopener noreferrer">
                      Watch the video (opens in a new tab)
                    </a>
                  </p>
                )}
                {lesson.content ? (
                  <p className="prewrap">{lesson.content}</p>
                ) : (
                  <p className="muted">This lesson has no text yet.</p>
                )}
                {error && (
                  <p role="alert" className="error">
                    {error}
                  </p>
                )}
                <div className="row wrap">
                  <button
                    type="button"
                    className={lesson.completed ? "secondary" : undefined}
                    disabled={busy}
                    aria-pressed={lesson.completed}
                    onClick={() => void setCompleted(!lesson.completed)}
                  >
                    {lesson.completed ? "Completed ✓ (undo)" : "Mark as complete"}
                  </button>
                  {lesson.quiz && (
                    <Link className="linkbtn secondary" href={`/quizzes/${lesson.quiz.id}?course=${id}`}>
                      Take quiz{lesson.quiz.best_score !== null ? ` (best ${lesson.quiz.best_score}%)` : ""}
                    </Link>
                  )}
                </div>
              </article>
            )}
          </ResourceView>
        )}
      </RequireAuth>
    </Shell>
  );
}
