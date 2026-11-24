"use client";

import { type KeyboardEvent, type ReactNode, useState } from "react";

import { apiFetch, apiForm } from "@sn/api";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { type ColumnInfo, type Row, type TableInfo, textOfValue as textOf } from "@sn/compounds/crudModel";
import Button from "@sn/elements/Button";

import { useRefApi } from "../../selection";
import CellFiles from "@sn/compounds/RecordFiles";
import JsonEditor from "@sn/compounds/JsonEditor";
import { RefCellDialog } from "../dialogs/RefCellDialog";
import { pickFiles } from "@sn/compounds/Dialogs";
import { changedValues, pathPk, rawPk, tableColumns } from "@sn/compounds/recordModel";

/** The unsaved edits of the dialog, handed over when a reference is picked in the Table tab. */
export interface PendingEdits {
  values: Record<string, string>;
  files: Record<string, File[]>;
}

interface RecordDialogProps {
  api: string;
  table: TableInfo;
  row: Row;
  onDone: () => void;
  onClose: () => void;
  /** Picks a record in the Table tab (the dialog is closed by the caller). Without it, the dialog's own picker. */
  onPickRef?: (column: ColumnInfo, pending: PendingEdits) => void;
}


/** The reason a save failed, as the person reads it. */
const messageOf = (failure: unknown) => (failure instanceof Error ? failure.message : "Not saved");

/** One record, full screen: edit its fields (a reference is picked from its table, a picture, audio or video is added to), save it,
 * or delete it. */
export default function RecordDialog({ api, table, row, onDone, onClose, onPickRef }: RecordDialogProps) {
  const key = rawPk(table, row);
  const columns = tableColumns(table);
  const base = `${api}/${encodeURIComponent(table.name)}`;
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(columns.map((c) => [c.name, textOf(row[c.name])])));
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const [picking, setPicking] = useState<ColumnInfo | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refApi = useRefApi(picking?.ref?.table, api);

  const save = async () => {
    setBusy(true);
    setError("");
    let added = false;
    try {
      // The files go first: a refused file stops the save before any value changes. A file that is added leaves the pending list.
      for (const [name, list] of Object.entries(files)) {
        for (const file of list) {
          const form = new FormData();
          form.append("file", file, file.name);
          try {
            await apiForm(`${base}/${pathPk(key)}/files/${encodeURIComponent(name)}`, form);
          } catch (failure) {
            throw new Error(`${file.name} was not added: ${messageOf(failure)}`);
          }
          added = true;
          setFiles((current) => ({ ...current, [name]: (current[name] ?? []).filter((pending) => pending !== file) }));
        }
      }
      const changed = Object.fromEntries(columns.filter((c) => values[c.name] !== textOf(row[c.name])).map((c) => [c.name, values[c.name]]));
      if (Object.keys(changed).length > 0) {
        try {
          const response = await apiFetch<{ results: { ok: boolean; error?: string }[] }>(`${base}/batch-update`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rows: [{ pk: key, values: changedValues(columns, changed) }] }),
          });
          if (!response.results[0]?.ok) throw new Error(response.results[0]?.error ?? "Not saved");
        } catch (failure) {
          throw new Error(`${added ? "The files were added, but the values were not saved: " : "The values were not saved: "}${messageOf(failure)}`);
        }
      }
      onDone();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setAsking(false);
    setBusy(true);
    setError("");
    try {
      await apiFetch(`${base}/${pathPk(key)}`, { method: "DELETE" });
      onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Not deleted");
    } finally {
      setBusy(false);
    }
  };

  const field = (column: ColumnInfo): ReactNode => {
    if (column.media) {
      const pending = files[column.name] ?? [];
      return (
        <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
            <CellFiles api={api} table={table.name} pk={pathPk(key)} column={column.name} all onError={setError} />
            <Button type="button" size="sm" variant="secondary" style={{ width: 32, height: 32, flex: "none", padding: 0, fontSize: 18, lineHeight: "30px" }} disabled={busy} aria-label={`Add ${column.media?.kind ?? "image"} files to ${column.name}`} title={`Add ${column.media?.kind ?? "image"} files`} onClick={() => pickFiles(column.media?.kind ?? "image", column.media?.accept, (list) => setFiles((current) => ({ ...current, [column.name]: [...(current[column.name] ?? []), ...list] })), setError)}>+</Button>
          </div>
          {pending.length ? <span className="muted">{pending.length} file(s) to add on save</span> : null}
        </div>
      );
    }
    if (column.ref) {
      return (
        <button
          type="button"
          aria-label={`Pick ${column.name}`}
          disabled={busy || column.readonly}
          onClick={() => (onPickRef ? onPickRef(column, pendingEdits()) : setPicking(column))}
          style={{ all: "unset", cursor: "pointer", textDecoration: "underline dotted", padding: "4px 0" }}
        >
          {labels[column.name] ?? values[column.name] ?? "—"}
        </button>
      );
    }
    if (column.type === "json") {
      return (
        <JsonEditor
          label={column.name}
          value={values[column.name] ?? ""}
          disabled={busy}
          onChange={(text) => setValues((current) => ({ ...current, [column.name]: text }))}
        />
      );
    }
    return (
      <input
        aria-label={column.name}
        value={values[column.name] ?? ""}
        disabled={busy}
        onChange={(event) => setValues((current) => ({ ...current, [column.name]: event.target.value }))}
        style={{ width: "100%", boxSizing: "border-box", padding: "8px 10px", background: "color-mix(in srgb, var(--line) 8%, transparent)", color: "inherit", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", borderRadius: 6 }}
      />
    );
  };

  const pendingEdits = (): PendingEdits => ({
    values: Object.fromEntries(columns.filter((c) => values[c.name] !== textOf(row[c.name])).map((c) => [c.name, values[c.name]])),
    files,
  });

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && !picking && !asking) onClose();
  };

  return (
    <div role="dialog" aria-modal="true" aria-label={`${table.label}: row ${key}`} onKeyDown={onKeyDown} style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", flexDirection: "column", background: "var(--solid-0)", color: "inherit" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 20px", borderBottom: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }}>
        <strong>{table.label} · {table.pk.join("~")} {key}</strong>
        <Button type="button" size="sm" variant="secondary" style={{ width: "auto", flex: "none" }} onClick={onClose}>Close</Button>
      </header>
      <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16, alignItems: "start" }}>
          {columns.filter((column) => !column.media).map((column) => (
            <div key={column.name} style={{ display: "grid", gap: 6, alignContent: "start" }}>
              <label htmlFor={`record-${column.name}`} className="muted" style={{ fontSize: 13 }}>{column.name}</label>
              <div id={`record-${column.name}`}>{field(column)}</div>
            </div>
          ))}
        </div>
        {columns.some((column) => column.media) ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16, alignItems: "start", marginTop: 24, paddingTop: 16, borderTop: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }}>
            {columns.filter((column) => column.media).map((column) => (
              <div key={column.name} style={{ display: "grid", gap: 8, alignContent: "start" }}>
                <label htmlFor={`record-${column.name}`} className="muted" style={{ fontSize: 13 }}>{column.name}</label>
                <div id={`record-${column.name}`}>{field(column)}</div>
              </div>
            ))}
          </div>
        ) : null}
        {error ? <p role="alert" style={{ marginTop: 16, fontWeight: 600, color: "var(--line)" }}>{error}</p> : null}
      </div>
      <footer style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "12px 20px", borderTop: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }}>
        <Button type="button" size="sm" variant="danger" style={{ width: "auto", flex: "none" }} disabled={busy} onClick={() => setAsking(true)}>Delete</Button>
        <div style={{ display: "flex", gap: 10 }}>
          <Button type="button" size="md" variant="secondary" style={{ width: "auto" }} disabled={busy} onClick={onClose}>Cancel</Button>
          <Button type="button" size="md" variant="primary" style={{ width: "auto" }} disabled={busy} onClick={() => void save()}>Save</Button>
        </div>
      </footer>
      {picking && picking.ref ? (
        <RefCellDialog
          api={refApi}
          table={picking.ref.table}
          label={picking.ref.label}
          keyColumn={picking.ref.key ?? "id"}
          first=""
          onPick={(value, text) => {
            setValues((current) => ({ ...current, [picking.name]: value }));
            setLabels((current) => ({ ...current, [picking.name]: text }));
            setPicking(null);
          }}
          onClose={() => setPicking(null)}
        />
      ) : null}
      <ConfirmModal open={asking} message="Delete this row? This cannot be undone." confirmLabel="Delete" cancelLabel="Cancel" onConfirm={() => void remove()} onCancel={() => setAsking(false)} />
    </div>
  );
}
