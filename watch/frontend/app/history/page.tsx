"use client";

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@sn/api";
import Gate from "../Gate";
import { formatDuration } from "../format";
import { API, HistoryItem } from "../types";

function History() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<HistoryItem[]>(`${API}/me/history`)
      .then(setItems)
      .catch((caught: unknown) =>
        setError(caught instanceof ApiError ? caught.message : "Could not load your history"),
      );
  }, []);

  if (error) {
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  }
  if (items === null) return <p role="status">Loading…</p>;
  if (items.length === 0) return <p className="muted">You have not watched anything yet.</p>;
  return (
    <ul className="grid">
      {items.map(({ video, seconds, updated_at }) => (
        <li key={video.id}>
          <article className="card stack">
            <h2 style={{ fontSize: "1.1rem", margin: 0 }}>
              <a href={`/watch/v/${video.id}`}>{video.title}</a>
            </h2>
            <span className="muted">
              Stopped at {formatDuration(seconds)} ·{" "}
              <time dateTime={updated_at}>{new Date(updated_at).toLocaleString()}</time>
            </span>
          </article>
        </li>
      ))}
    </ul>
  );
}

export default function HistoryPage() {
  return <Gate title="History">{() => <History />}</Gate>;
}
