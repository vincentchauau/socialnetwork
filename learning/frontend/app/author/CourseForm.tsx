"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, CourseSummary, LEVELS, Level, errorText } from "../lib";

const TITLE_MAX = 120;
const SUMMARY_MAX = 1000;
const MAX_TAGS = 10;

interface Props {
  initial?: CourseSummary;
  onSaved: (course: CourseSummary) => void;
}

function parseTags(raw: string): string[] {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

export function CourseForm({ initial, onSaved }: Props) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [summary, setSummary] = useState(initial?.summary ?? "");
  const [level, setLevel] = useState<Level>(initial?.level ?? "beginner");
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [published, setPublished] = useState(initial?.published ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const tagList = parseTags(tags);
    if (tagList.length > MAX_TAGS) {
      setError(`Use at most ${MAX_TAGS} tags`);
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const course = await apiFetch<CourseSummary>(
        initial ? `${API}/courses/${initial.id}` : `${API}/courses`,
        {
          method: initial ? "PATCH" : "POST",
          body: JSON.stringify({ title, summary, level, tags: tagList, published }),
        },
      );
      setSaved(true);
      onSaved(course);
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
        Summary
        <textarea value={summary} maxLength={SUMMARY_MAX} onChange={(e) => setSummary(e.target.value)} />
      </label>
      <label>
        Level
        <select value={level} onChange={(e) => setLevel(e.target.value as Level)}>
          {LEVELS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tags (comma separated, up to {MAX_TAGS})
        <input value={tags} onChange={(e) => setTags(e.target.value)} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} />
        Published (drafts are visible only to you)
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
        {busy ? "Saving…" : initial ? "Save course" : "Create course"}
      </button>
    </form>
  );
}
