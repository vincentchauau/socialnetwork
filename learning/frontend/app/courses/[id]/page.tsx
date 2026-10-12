"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { apiFetch } from "@sn/api";
import {
  API,
  CourseDetail,
  ProgressBar,
  ResourceView,
  Shell,
  errorText,
  useAuth,
  useResource,
} from "../../lib";

export default function CoursePage() {
  const { id } = useParams<{ id: string }>();
  const auth = useAuth();
  const [state, reload] = useResource<CourseDetail>(`/courses/${id}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signedIn = auth.status === "signed-in";

  async function toggleEnrolment(enrolled: boolean) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`${API}/courses/${id}/enroll`, { method: enrolled ? "DELETE" : "POST" });
      reload();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Course">
      <ResourceView state={state}>
        {(course) => (
          <div className="stack">
            <h2>{course.title}</h2>
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
              By {course.owner_username} · {course.enrolment_count} enrolled
            </p>
            {course.summary && <p className="prewrap">{course.summary}</p>}

            {course.enrolled && (
              <ProgressBar percent={course.progress_percent} label="Course progress" />
            )}
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <div className="row wrap">
              {auth.status === "anonymous" && (
                <p>
                  <a href="/login">Sign in</a> to enrol.
                </p>
              )}
              {signedIn && course.published && !course.is_owner && (
                <button
                  type="button"
                  className={course.enrolled ? "secondary" : undefined}
                  disabled={busy}
                  onClick={() => void toggleEnrolment(course.enrolled)}
                >
                  {course.enrolled ? "Unenrol" : "Enrol"}
                </button>
              )}
              {course.enrolled && (
                <Link className="linkbtn secondary" href={`/courses/${course.id}/certificate`}>
                  Certificate
                </Link>
              )}
              {course.is_owner && (
                <Link className="linkbtn secondary" href={`/author/${course.id}`}>
                  Edit course
                </Link>
              )}
            </div>

            <h2>Outline</h2>
            {course.lessons.length === 0 ? (
              <p className="muted">No lessons yet.</p>
            ) : (
              <ol className="list" aria-label="Lessons">
                {course.lessons.map((lesson) => (
                  <li key={lesson.id} className="card row wrap">
                    {course.enrolled || course.is_owner ? (
                      <Link href={`/courses/${course.id}/lessons/${lesson.id}`}>
                        {lesson.position}. {lesson.title}
                      </Link>
                    ) : (
                      <span>
                        {lesson.position}. {lesson.title}
                      </span>
                    )}
                    {lesson.has_quiz && <span className="pill">quiz</span>}
                    {lesson.completed && <span className="pill">done ✓</span>}
                  </li>
                ))}
              </ol>
            )}
            {!course.enrolled && !course.is_owner && course.lessons.length > 0 && (
              <p className="muted">Enrol to read the lessons.</p>
            )}
          </div>
        )}
      </ResourceView>
    </Shell>
  );
}
