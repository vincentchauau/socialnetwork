"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Field, JobCard, Protected, Status } from "./components";
import {
  API,
  EMPLOYMENT_LABELS,
  EmploymentType,
  LIMITS,
  PostingPage,
  PostingSummary,
  errorText,
} from "./lib";

interface Filters {
  q: string;
  location: string;
  remote: "" | "true" | "false";
  type: "" | EmploymentType;
  min_salary: string;
  tag: string;
}

const EMPTY_FILTERS: Filters = {
  q: "",
  location: "",
  remote: "",
  type: "",
  min_salary: "",
  tag: "",
};
const PAGE_SIZE = 20;

function buildQuery(filters: Filters, cursor: string | null): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

function Search() {
  const [form, setForm] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [items, setItems] = useState<PostingSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiFetch<PostingPage>(`${API}/jobs?${buildQuery(filters, null)}`)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setCursor(page.next_cursor);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errorText(e, "Could not load jobs"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setFilters(form);
  }

  function reset() {
    setForm(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
  }

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await apiFetch<PostingPage>(`${API}/jobs?${buildQuery(filters, cursor)}`);
      setItems((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) {
      setError(errorText(e, "Could not load more jobs"));
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <>
      <form className="stack card" onSubmit={submit} role="search" aria-label="Search jobs">
        <div className="row wrap">
          <Field label="Keywords" grow>
            <input
              type="search"
              maxLength={LIMITS.query}
              value={form.q}
              onChange={(e) => update("q", e.target.value)}
            />
          </Field>
          <Field label="Location" grow>
            <input
              maxLength={LIMITS.location}
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
            />
          </Field>
        </div>
        <div className="row wrap">
          <Field label="Work mode" grow>
            <select value={form.remote} onChange={(e) => update("remote", e.target.value as Filters["remote"])}>
              <option value="">Any</option>
              <option value="true">Remote</option>
              <option value="false">On site</option>
            </select>
          </Field>
          <Field label="Type" grow>
            <select value={form.type} onChange={(e) => update("type", e.target.value as Filters["type"])}>
              <option value="">Any</option>
              {Object.entries(EMPLOYMENT_LABELS).map(([value, text]) => (
                <option key={value} value={value}>{text}</option>
              ))}
            </select>
          </Field>
        </div>
        <div className="row wrap">
          <Field label="Minimum salary" grow>
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={form.min_salary}
              onChange={(e) => update("min_salary", e.target.value)}
            />
          </Field>
          <Field label="Tag" grow>
            <input value={form.tag} maxLength={30} onChange={(e) => update("tag", e.target.value)} />
          </Field>
        </div>
        <div className="row wrap">
          <button>Search</button>
          <button type="button" className="secondary" onClick={reset}>Reset</button>
        </div>
      </form>

      <Status
        loading={loading}
        error={error}
        empty={items.length === 0}
        emptyText="No jobs match your search."
      />

      {!loading && items.length > 0 && (
        <ul className="list" aria-label="Search results">
          {items.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </ul>
      )}

      {!loading && cursor && (
        <button className="secondary" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </>
  );
}

export default function SearchPage() {
  return <Protected title="Jobs">{() => <Search />}</Protected>;
}
