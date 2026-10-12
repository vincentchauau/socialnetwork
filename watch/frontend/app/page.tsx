"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@sn/api";
import Gate from "./Gate";
import VideoList from "./VideoList";
import { API, Video, VideoPage } from "./types";

const PAGE_SIZE = 12;

function buildUrl(query: string, tag: string, cursor: number | null): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (query) params.set("q", query);
  if (tag) params.set("tag", tag);
  if (cursor !== null) params.set("cursor", String(cursor));
  return `${API}/videos?${params.toString()}`;
}

function Catalog() {
  const [draft, setDraft] = useState("");
  const [tagDraft, setTagDraft] = useState("");
  const [filters, setFilters] = useState({ query: "", tag: "" });
  const [videos, setVideos] = useState<Video[]>([]);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (cursor: number | null, query: string, tag: string) => {
      setLoading(true);
      setError(null);
      try {
        const page = await apiFetch<VideoPage>(buildUrl(query, tag, cursor));
        setVideos((current) => (cursor === null ? page.items : [...current, ...page.items]));
        setNextCursor(page.next_cursor);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "Could not load videos");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load(null, filters.query, filters.tag);
  }, [load, filters]);

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setFilters({ query: draft.trim(), tag: tagDraft.trim().toLowerCase() });
  }

  return (
    <>
      <form className="stack" onSubmit={onSearch} role="search" aria-label="Search videos">
        <div className="row wrap">
          <label className="muted" htmlFor="q">
            Search
          </label>
          <input
            id="q"
            type="search"
            value={draft}
            maxLength={100}
            placeholder="Title or tag"
            onChange={(event) => setDraft(event.target.value)}
          />
          <label className="muted" htmlFor="tag">
            Tag
          </label>
          <input
            id="tag"
            value={tagDraft}
            maxLength={30}
            placeholder="Exact tag"
            onChange={(event) => setTagDraft(event.target.value)}
          />
          <button type="submit">Search</button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading && videos.length === 0 && <p role="status">Loading…</p>}
      {!(loading && videos.length === 0) && !error && (
        <VideoList
          videos={videos}
          empty={
            filters.query || filters.tag
              ? "No videos match your search."
              : "No videos yet. Be the first to upload one."
          }
        />
      )}
      {nextCursor !== null && (
        <button
          type="button"
          className="secondary"
          disabled={loading}
          onClick={() => void load(nextCursor, filters.query, filters.tag)}
        >
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </>
  );
}

export default function CatalogPage() {
  return <Gate title="Watch">{() => <Catalog />}</Gate>;
}
