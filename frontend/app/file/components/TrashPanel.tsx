"use client";

import { useCallback, useEffect, useState } from "react";

import { httpErrorText as errorText } from "@sn/api";
import Button from "@sn/elements/Button";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { intlLocale } from "@sn/lib/i18n";

import { eraseTrash, listTrash, restoreTrash } from "../lib/api";
import { formatBytes } from "../lib/paths";
import type { TrashEntry } from "../lib/types";
import { tr } from "../i18n";

const when = (seconds: number): string => new Date(seconds * 1000).toLocaleString(intlLocale(), { dateStyle: "short", timeStyle: "short" });

/** What the person deleted: each item can be put back where it was, or erased for good; all of it can be emptied. It is erased after a while by itself. */
export default function TrashPanel({ onRestored }: { onRestored: () => void }) {
  const [entries, setEntries] = useState<TrashEntry[] | null>(null);
  const [keepDays, setKeepDays] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [asking, setAsking] = useState<"all" | TrashEntry | null>(null);

  const load = useCallback(async () => {
    try {
      const found = await listTrash();
      setEntries(found.entries);
      setKeepDays(found.keepDays);
    } catch (caught) {
      setError(errorText(caught));
      setEntries([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function restore(entry: TrashEntry) {
    setError(null);
    try {
      const placed = await restoreTrash(entry.id);
      setNotice(tr("trash_restored_p0_p1", { p0: placed.name, p1: placed.path }));
      onRestored();
    } catch (caught) {
      setError(errorText(caught));
    }
    await load();
  }

  async function erase(target: "all" | TrashEntry) {
    setAsking(null);
    setError(null);
    try {
      await eraseTrash(target === "all" ? undefined : target.id);
      setNotice(null);
    } catch (caught) {
      setError(errorText(caught));
    }
    await load();
  }

  return (
    <section aria-label={tr("trash")} className="stack" style={{ padding: 8 }}>
      <p className="muted" style={{ margin: 0 }}>{tr("trash_hint_p0", { p0: keepDays })}</p>
      {notice ? <p role="status" style={{ margin: 0 }}>{notice}</p> : null}
      {error ? <p role="alert" className="error" style={{ margin: 0 }}>{error}</p> : null}
      {entries === null ? <p role="status" className="muted" style={{ margin: 0 }}>…</p> : null}
      {entries !== null && entries.length === 0 ? <p className="muted" style={{ margin: 0 }}>{tr("trash_empty")}</p> : null}
      {entries !== null && entries.length > 0 ? (
        <>
          <div><Button type="button" size="sm" variant="secondary" onClick={() => setAsking("all")}>{tr("trash_empty_all")}</Button></div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
            {entries.map((entry) => (
              <li key={entry.id} className="card" style={{ padding: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span aria-hidden="true">{entry.type === "folder" ? "📁" : "📄"}</span>
                <strong style={{ flex: "1 1 160px", minWidth: 0, overflowWrap: "anywhere" }}>{entry.name}</strong>
                <span className="muted">{entry.parent} · {formatBytes(entry.size)} · {when(entry.deletedAt)}</span>
                <Button type="button" size="sm" onClick={() => void restore(entry)}>{tr("trash_restore")}</Button>
                <Button type="button" size="sm" variant="secondary" onClick={() => setAsking(entry)}>{tr("trash_erase")}</Button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <ConfirmModal
        open={asking !== null}
        message={asking === "all" ? tr("trash_confirm_all") : tr("trash_confirm_one_p0", { p0: asking?.name ?? "" })}
        confirmLabel={tr("trash_erase")}
        cancelLabel={tr("huy")}
        onCancel={() => setAsking(null)}
        onConfirm={() => asking && void erase(asking)}
      />
    </section>
  );
}
