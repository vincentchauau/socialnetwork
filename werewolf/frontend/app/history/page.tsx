"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@sn/api";
import AuthGate from "../AuthGate";
import { HistoryEntry, roleLabel } from "../game";
import type { Role } from "../game";

const API = "/api/werewolf";

function History() {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<HistoryEntry[]>(`${API}/me/history`)
      .then(setEntries)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load your history"),
      );
  }, []);

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Game history</h1>
        <a href="/">← Home</a>
      </div>
      <Link href="/">Back to lobby</Link>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {entries === null && !error && <p className="muted">Loading…</p>}
      {entries?.length === 0 && <p className="muted">You have not finished a game yet.</p>}
      <ul className="stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {entries?.map((entry) => (
          <li key={`${entry.room_id}-${entry.finished_at}`} className="card stack">
            <strong>
              {entry.won ? "Won" : "Lost"} as {roleLabel(entry.your_role as Role)}
            </strong>
            <span className="muted">
              {entry.winner === "village" ? "Village" : "Werewolves"} won after {entry.days}{" "}
              {entry.days === 1 ? "day" : "days"} ·{" "}
              {new Date(entry.finished_at).toLocaleString()}
            </span>
            <span style={{ overflowWrap: "anywhere" }}>
              {entry.players
                .map(
                  (p) => `${p.username} (${roleLabel(p.role as Role)}${p.survived ? "" : ", dead"})`,
                )
                .join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function HistoryPage() {
  return (
    <AuthGate title="Game history">{() => <History />}</AuthGate>
  );
}
