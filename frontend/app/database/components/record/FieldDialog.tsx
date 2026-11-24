"use client";

import { useState } from "react";

import { apiFetch, apiForm } from "@sn/api";
import { type ColumnInfo, type Row, type TableInfo, textOfValue } from "@sn/compounds/crudModel";

import { RefCellDialog } from "../dialogs/RefCellDialog";
import { Dialog, FileCellDialog } from "@sn/compounds/Dialogs";
import { useRefApi } from "../../selection";
import { changedValues, pathPk, rawPk } from "@sn/compounds/recordModel";

interface FieldDialogProps {
  api: string;
  table: TableInfo;
  row: Row;
  column: ColumnInfo;
  onDone: () => void;
  onClose: () => void;
}

/** One field of one row, changed by a double click on it in the Grid: a text, a reference (a record picked) or a file (uploaded). */
export default function FieldDialog({ api, table, row, column, onDone, onClose }: FieldDialogProps) {
  const base = `${api}/${encodeURIComponent(table.name)}`;
  const refApi = useRefApi(column.ref?.table, api);
  const key = rawPk(table, row);
  const [text, setText] = useState(textOfValue(row[column.name]));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState<"file" | "ref" | null>(column.media ? "file" : column.ref ? "ref" : null);

  const saveValue = async (value: string) => {
    setBusy(true);
    setError("");
    try {
      const response = await apiFetch<{ results: { ok: boolean; error?: string }[] }>(`${base}/batch-update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: [{ pk: key, values: changedValues([column], { [column.name]: value }) }] }),
      });
      if (response.results[0]?.ok) onDone();
      else setError(response.results[0]?.error ?? "Not saved");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Not saved");
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async (list: File[]) => {
    setBusy(true);
    setError("");
    try {
      for (const file of list) {
        const form = new FormData();
        form.append("file", file, file.name);
        await apiForm(`${base}/${pathPk(key)}/files/${encodeURIComponent(column.name)}`, form);
      }
      onDone();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The file could not be uploaded.");
    } finally {
      setBusy(false);
    }
  };

  if (picking === "file" && column.media) {
    return <FileCellDialog kind={column.media.kind ?? "image"} accept={column.media.accept} onPick={(list) => void uploadFiles(list)} onClose={onClose} />;
  }
  if (picking === "ref" && column.ref) {
    return (
      <RefCellDialog
        api={refApi}
        table={column.ref.table}
        label={column.ref.label}
        keyColumn={column.ref.key ?? "id"}
        first=""
        onPick={(value) => void saveValue(value)}
        onClose={onClose}
      />
    );
  }
  return (
    <Dialog label={`${column.name} of row ${key}`} onClose={onClose}>
      <input aria-label={column.name} value={text} onChange={(event) => setText(event.target.value)} autoFocus style={{ width: "100%" }} />
      {error ? <p role="alert" style={{ margin: 0 }}>{error}</p> : null}
      <div><button type="button" onClick={() => void saveValue(text)} disabled={busy}>Save</button></div>
    </Dialog>
  );
}
