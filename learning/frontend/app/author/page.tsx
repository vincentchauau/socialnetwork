"use client";

import Link from "next/link";

import { CourseSummary, RequireAuth, ResourceView, Shell, useAuth, useResource } from "../lib";

export default function AuthorPage() {
  const auth = useAuth();
  const [state] = useResource<CourseSummary[]>(auth.status === "signed-in" ? "/me/authored" : null);
  return (
    <Shell title="Teach">
      <RequireAuth auth={auth}>
        {() => (
          <div className="stack">
            <Link className="linkbtn" href="/author/new">
              Create a course
            </Link>
            <ResourceView state={state}>
              {(courses) =>
                courses.length === 0 ? (
                  <p className="muted">You have not created any course yet.</p>
                ) : (
                  <ul className="list" aria-label="My courses">
                    {courses.map((course) => (
                      <li key={course.id} className="card row wrap">
                        <Link href={`/author/${course.id}`}>{course.title}</Link>
                        <span className="pill">{course.published ? "published" : "draft"}</span>
                        <span className="muted">
                          {course.lesson_count} lessons · {course.enrolment_count} enrolled
                        </span>
                      </li>
                    ))}
                  </ul>
                )
              }
            </ResourceView>
          </div>
        )}
      </RequireAuth>
    </Shell>
  );
}
