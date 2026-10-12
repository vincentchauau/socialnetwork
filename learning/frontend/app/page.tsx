"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { API, CourseCard, CourseSummary, LEVELS, Shell, errorText } from "./lib";

interface Page {
  items: CourseSummary[];
  next_cursor: number | null;
}

interface Filters {
  q: string;
  level: string;
  tag: string;
}

const EMPTY_FILTERS: Filters = { q: "", level: "", tag: "" };

function buildQuery(filters: Filters, cursor: number | null): string {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.level) params.set("level", filters.level);
  if (filters.tag.trim()) params.set("tag", filters.tag.trim());
  if (cursor !== null) params.set("cursor", String(cursor));
  const query = params.toString();
  return `${API}/courses${query ? `?${query}` : ""}`;
}

export default function CataloguePage() {
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [items, setItems] = useState<CourseSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (filters: Filters, cursor: number | null) => {
    setLoading(true);
    setError(null);
    try {
      const page = await apiFetch<Page>(buildQuery(filters, cursor));
      setItems((current) => (cursor === null ? page.items : [...current, ...page.items]));
      setNextCursor(page.next_cursor);
    } catch (caught) {
      setError(errorText(caught, "Could not load courses"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(applied, null);
  }, [applied, load]);

  function search(event: FormEvent) {
    event.preventDefault();
    setApplied(draft);
  }

  return (
    <Shell title="Courses">
      <form className="stack" onSubmit={search} role="search" aria-label="Search courses">
        <label>
          Search
          <input
            type="search"
            value={draft.q}
            maxLength={100}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
          />
        </label>
        <div className="row">
          <label style={{ flex: 1 }}>
            Level
            <select
              value={draft.level}
              onChange={(event) => setDraft({ ...draft, level: event.target.value })}
            >
              <option value="">Any level</option>
              {LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </label>
          <label style={{ flex: 1 }}>
            Tag
            <input
              value={draft.tag}
              maxLength={30}
              onChange={(event) => setDraft({ ...draft, tag: event.target.value })}
            />
          </label>
        </div>
        <button type="submit">Search</button>
      </form>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!loading && !error && items.length === 0 && <p className="muted">No courses found.</p>}
      <ul className="list" aria-label="Courses">
        {items.map((course) => (
          <CourseCard key={course.id} course={course} />
        ))}
      </ul>
      {loading && (
        <p className="muted" role="status">
          Loading…
        </p>
      )}
      {!loading && nextCursor !== null && (
        <button type="button" className="secondary" onClick={() => void load(applied, nextCursor)}>
          Load more
        </button>
      )}
    </Shell>
  );
}
