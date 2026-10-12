"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { apiFetch } from "@sn/api";
import { QuizBuilder } from "../../../QuizBuilder";
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

const TITLE_MAX = 120;
const CONTENT_MAX = 20000;
const VIDEO_MAX = 500;

function LessonForm({ courseId, lesson }: { courseId: string; lesson?: Lesson }) {
  const router = useRouter();
  const [title, setTitle] = useState(lesson?.title ?? "");
  const [content, setContent] = useState(lesson?.content ?? "");
  const [videoUrl, setVideoUrl] = useState(lesson?.video_url ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const trimmedUrl = videoUrl.trim();
    if (trimmedUrl && !trimmedUrl.startsWith("https://")) {
      setError("The video link must start with https://");
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const body = JSON.stringify({ title, content, video_url: trimmedUrl || null });
      const result = await apiFetch<Lesson>(
        lesson ? `${API}/courses/${courseId}/lessons/${lesson.id}` : `${API}/courses/${courseId}/lessons`,
        { method: lesson ? "PATCH" : "POST", body },
      );
      setSaved(true);
      if (!lesson) router.replace(`/author/${courseId}/lessons/${result.id}`);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <label>
        Title
        <input value={title} required maxLength={TITLE_MAX} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Content (plain text)
        <textarea
          value={content}
          maxLength={CONTENT_MAX}
          rows={12}
          onChange={(e) => setContent(e.target.value)}
        />
      </label>
      <label>
        Video link (https only, optional)
        <input
          type="url"
          value={videoUrl}
          maxLength={VIDEO_MAX}
          onChange={(e) => setVideoUrl(e.target.value)}
        />
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="ok">
          Saved.
        </p>
      )}
      <button type="submit" disabled={busy}>
        {busy ? "Saving…" : lesson ? "Save lesson" : "Create lesson"}
      </button>
    </form>
  );
}

function ExistingLesson({ courseId, lessonId }: { courseId: string; lessonId: string }) {
  const [state] = useResource<Lesson>(`/courses/${courseId}/lessons/${lessonId}`);
  return (
    <ResourceView state={state}>
      {(lesson) => (
        <div className="stack">
          <LessonForm courseId={courseId} lesson={lesson} />
          <h2>Quiz</h2>
          <QuizBuilder courseId={courseId} lessonId={lesson.id} quizId={lesson.quiz?.id ?? null} />
        </div>
      )}
    </ResourceView>
  );
}

export default function EditLessonPage() {
  const { id, lessonId } = useParams<{ id: string; lessonId: string }>();
  const auth = useAuth();
  return (
    <Shell title={lessonId === "new" ? "New lesson" : "Edit lesson"}>
      <p>
        <Link href={`/author/${id}`}>← Back to course editor</Link>
      </p>
      <RequireAuth auth={auth}>
        {() =>
          lessonId === "new" ? (
            <LessonForm courseId={id} />
          ) : (
            <ExistingLesson courseId={id} lessonId={lessonId} />
          )
        }
      </RequireAuth>
    </Shell>
  );
}
