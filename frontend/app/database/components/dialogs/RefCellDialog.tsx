"use client";

import { type KeyboardEvent, useEffect, useState } from "react";

import { apiFetch } from "@sn/api";
import { Dialog } from "@sn/compounds/Dialogs";

/** Opened on a reference cell: the referenced table itself, with every column of its records, so the person can check the other
 * columns of a record before choosing it. A search narrows it; a click on a row picks that record. */
export function RefCellDialog({ api, table, label, keyColumn, first, onPick, onClose }: {
  api: string; table: string; label: string; keyColumn: string; first: string;
  onPick: (key: string, text: string) => void; onClose: () => void;
}) {
  const [query, setQuery] = useState(first);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    apiFetch<{ name: string; columns: { name: string; type: string; secret: boolean; media?: unknown }[] }[]>(`${api}/tables`)
      .then((tables) => {
        const found = tables.find((t) => t.name === table);
        if (alive) setColumns((found?.columns ?? []).filter((c) => !c.secret && c.type !== "bytes" && !c.media).map((c) => c.name));
      })
      .catch(() => { if (alive) setColumns([]); });
    return () => { alive = false; };
  }, [api, table]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      apiFetch<{ rows: Record<string, unknown>[] }>(`${api}/${encodeURIComponent(table)}?q=${encodeURIComponent(query)}&limit=50`, { signal: controller.signal })
        .then((response) => { setRows(response.rows); setError(""); })
        .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Could not search."); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, table, query]);

  const shownColumns = columns.length ? columns : [keyColumn, label];
  const textOf = (value: unknown) => (value == null ? "" : String(value));
  return (
    <Dialog label={`Choose a ${table} record`} onClose={onClose}>
      <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label={`Search ${table}`} autoFocus style={{ width: "100%" }} />
      {error ? <p role="alert" style={{ margin: 0 }}>{error}</p> : null}
      <div style={{ overflow: "auto", maxHeight: "60vh", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", borderRadius: 6 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr>{shownColumns.map((name) => <th key={name} scope="col" style={{ textAlign: "left", padding: "6px 8px", whiteSpace: "nowrap", position: "sticky", top: 0, background: "var(--solid-0)" }}>{name}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={textOf(row[keyColumn])} onClick={() => onPick(textOf(row[keyColumn]), textOf(row[label] ?? row[keyColumn]))} style={{ cursor: "pointer" }}>
                {shownColumns.map((name) => <td key={name} style={{ padding: "6px 8px", borderTop: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", whiteSpace: "nowrap" }}>{textOf(row[name])}</td>)}
              </tr>
            ))}
            {rows.length === 0 && !error ? <tr><td colSpan={shownColumns.length} className="muted" style={{ padding: 8 }}>No record matches.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </Dialog>
  );
}
