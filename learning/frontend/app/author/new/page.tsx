"use client";

import { useRouter } from "next/navigation";

import { CourseForm } from "../CourseForm";
import { RequireAuth, Shell, useAuth } from "../../lib";

export default function NewCoursePage() {
  const auth = useAuth();
  const router = useRouter();
  return (
    <Shell title="New course">
      <RequireAuth auth={auth}>
        {() => <CourseForm onSaved={(course) => router.push(`/author/${course.id}`)} />}
      </RequireAuth>
    </Shell>
  );
}
