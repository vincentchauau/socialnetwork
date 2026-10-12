"use client";

import { CourseCard, CourseSummary, RequireAuth, ResourceView, Shell, useAuth, useResource } from "../lib";

function CourseList({ path, empty, label }: { path: string; empty: string; label: string }) {
  const [state] = useResource<CourseSummary[]>(path);
  return (
    <ResourceView state={state}>
      {(courses) =>
        courses.length === 0 ? (
          <p className="muted">{empty}</p>
        ) : (
          <ul className="list" aria-label={label}>
            {courses.map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </ul>
        )
      }
    </ResourceView>
  );
}

export default function MyLearningPage() {
  const auth = useAuth();
  return (
    <Shell title="My learning">
      <RequireAuth auth={auth}>
        {() => (
          <CourseList
            path="/me/courses"
            label="Courses I am taking"
            empty="You have not enrolled in any course yet. Browse the catalogue to start."
          />
        )}
      </RequireAuth>
    </Shell>
  );
}
