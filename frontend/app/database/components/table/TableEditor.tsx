"use client";

import { type ChangeEvent, type KeyboardEvent, type MouseEvent, useEffect, useRef, useState } from "react";

import { apiFetch, apiForm } from "@sn/api";
import { ConfirmModal } from "@sn/compounds/Dialogs";
import { type ColumnInfo, type Labels, type Row, type TableInfo, pkOf, textOfValue } from "@sn/compounds/crudModel";

import { RefCellDialog } from "../dialogs/RefCellDialog";
import { CellView } from "@sn/compounds/CellView";
import JsonEditor from "@sn/compounds/JsonEditor";
import { FileCellDialog, fileCellText, pickFiles } from "@sn/compounds/Dialogs";
import { useDatabaseSelection, useRefApi } from "../../selection";
import { useRefPick } from "../refs/refPick";
import RecordDialog, { type PendingEdits } from "../record/RecordDialog";
import { MediaView } from "@sn/compounds/FileTools";
import CellFiles from "@sn/compounds/RecordFiles";
import Button from "@sn/elements/Button";
import { useTableImport } from "./tableImport";
import { ColumnsMenu } from "@sn/compounds/TableFooter";
import { PageBar, SelectAllBar } from "@sn/compounds/TableFooter";
import { galleryTr } from "@sn/compounds/galleryModel";
import TextBox from "@sn/elements/TextBox";
import { CONTROL } from "@sn/compounds/GalleryView";
import { crudTr } from "@sn/compounds/crudModel";
import { TABLE_MAX_ROWS, changedValues, filesFor, folderPlan, pathPk, rawPk, tableColumns, titleColumn } from "@sn/compounds/recordModel";

interface Page {
  rows: Row[];
  total: number;
  labels?: Labels;
}

interface CellDialog {
  key: string;
  column: ColumnInfo;
  first: string;
}

type Batch<T> = { results: { index: number; ok: boolean; error?: string; row?: T }[]; created?: number; updated?: number };

/** A read-only cell: a json column is shown as CellView does (a summary, the full json on click); every other value as its text. */
function tableCell(table: TableInfo, columns: ColumnInfo[], row: Row, name: string) {
  const column = columns.find((candidate) => candidate.name === name);
  if (column?.type === "json") return <CellView column={column} value={row[name]} table={table} row={row} />;
  return String(row[name]);
}

/** The table as a table: rows are typed or pasted like a spreadsheet, files and references picked in their cells, rows added from
 * an Excel file or a folder, then everything saved together. A double click opens one row to edit or delete it. */
export default function TableEditor({ api, table, database }: { api: string; table: TableInfo; database: string }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const allColumns = tableColumns(table);
  const columns = allColumns.filter((column) => !hidden.has(column.name));
  const visibleKeys = table.pk.filter((name) => !hidden.has(name));
  const canEdit = table.writable;
  const base = `${api}/${encodeURIComponent(table.name)}`;
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  const [query, setQuery] = useState("");
  const [reload, setReload] = useState(0);
  const [page, setPage] = useState<Page>({ rows: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [changes, setChanges] = useState<Record<string, Record<string, string>>>({});
  const [files, setFiles] = useState<Record<string, Record<string, File[]>>>({});
  const [refTexts, setRefTexts] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [cellDialog, setCellDialog] = useState<CellDialog | null>(null);
  const [asking, setAsking] = useState(false);
  const [notice, setNotice] = useState("");
  const folderInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [recordRow, setRecordRow] = useState<Row | null>(null);
  const [reopenKey, setReopenKey] = useState<string | null>(null);
  const refApi = useRefApi(cellDialog?.column.ref?.table, api);
  const selection = useDatabaseSelection();
  const pick = useRefPick();
  // The record picker: when this table is the one a cell asked a record from, its rows are clickable to choose one.
  const choosing = pick?.active && pick.active.target.database === database && pick.active.target.table === table.name ? pick.active.target : null;

  // Back from a record picker: the unsaved changes of this table and the record chosen for it are put back.
  // A reference picked from the record dialog: the dialog closes, its unsaved edits go into the stash, and the Table tab shows the
  // referenced table. The record chosen comes back to this row's cell.
  const pickFromDialog = (row: Row, column: ColumnInfo, pending: PendingEdits) => {
    if (!pick || !column.ref) return;
    const key = pkOf(table, row);
    const owner = selection?.tables.find((t) => t.name === column.ref?.table)?.database ?? database;
    setRecordRow(null);
    pick.start(
      { database, table: table.name, key, column: column.name },
      { database: owner, table: column.ref.table, keyColumn: column.ref.key ?? "id", labelColumn: column.ref.label },
      { changes: { ...changes, [key]: { ...changes[key], ...pending.values } }, files: { ...files, [key]: { ...files[key], ...pending.files } }, refTexts, reopen: key },
    );
  };

  // The record dialog that asked for the reference opens again on its row, once the rows are loaded.
  useEffect(() => {
    if (!reopenKey) return;
    const found = page.rows.find((row) => pkOf(table, row) === reopenKey);
    if (!found) return;
    setRecordRow(found);
    setReopenKey(null);
  }, [reopenKey, page.rows, table]);

  useEffect(() => {
    if (!pick) return;
    const stash = pick.takeStash(database, table.name);
    const result = pick.takeResult(database, table.name);
    if (!stash && !result) return;
    const restored = stash ?? { changes: {}, files: {}, refTexts: {} };
    let nextChanges = restored.changes;
    let nextTexts = restored.refTexts;
    if (result) {
      const { origin, value, text } = result;
      nextChanges = { ...nextChanges, [origin.key]: { ...nextChanges[origin.key], [origin.column]: value } };
      nextTexts = { ...nextTexts, [`${origin.key}:${origin.column}`]: text };
    }
    setChanges(nextChanges);
    setFiles(restored.files);
    setRefTexts(nextTexts);
    setReopenKey(restored.reopen ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, when the table is shown again
  }, []);

  // A reference cell asks for its record: the Table tab shows the table it points to, in the app that owns it. Without the
  // picker, the cell's own dialog.
  const askRecord = (key: string, column: ColumnInfo, first: string) => {
    if (column.media) {
      pickFiles(column.media.kind ?? "image", column.media.accept, (list) => addFiles(key, column.name, list), setNotice);
      return;
    }
    if (pick && column.ref) {
      const owner = selection?.tables.find((t) => t.name === column.ref?.table)?.database ?? database;
      pick.start(
        { database, table: table.name, key, column: column.name },
        { database: owner, table: column.ref.table, keyColumn: column.ref.key ?? "id", labelColumn: column.ref.label },
        { changes, files, refTexts },
      );
      return;
    }
    setCellDialog({ key, column, first });
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    apiFetch<Page>(`${base}?offset=${offset}&limit=${pageSize}&q=${encodeURIComponent(query)}`)
      .then((response) => { if (alive) { setPage(response); setError(""); } })
      .catch((failure: unknown) => { if (alive) setError(failure instanceof Error ? failure.message : "The rows could not be loaded."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [base, offset, pageSize, query, reload]);

  const shown = (key: string, row: Row | null, column: ColumnInfo): string => {
    const edited = changes[key]?.[column.name];
    // A file cell shows its pictures, audio and video, never its text: the text is shown only while a key is typed into it.
    if (column.media) return "";
    if (edited !== undefined) return column.ref ? (refTexts[`${key}:${column.name}`] ?? edited) : edited;
    const raw = row?.[column.name];
    const text = textOfValue(raw);
    if (column.ref) return page.labels?.[column.name]?.[text] ?? text;
    return text;
  };

  const storedValue = (key: string, row: Row | null, column: ColumnInfo): string => {
    const typed = changes[key]?.[column.name];
    if (typed !== undefined) return typed;
    return textOfValue(row?.[column.name]);
  };

  const setChange = (key: string, column: string, text: string) => {
    setChanges((current) => ({ ...current, [key]: { ...current[key], [column]: text } }));
  };

  const addFiles = (key: string, column: string, list: File[]) =>
    setFiles((current) => ({ ...current, [key]: { ...current[key], [column]: [...(current[key]?.[column] ?? []), ...list] } }));

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>, key: string, column: ColumnInfo) => {
    const typed = event.key.length === 1 && !event.ctrlKey && !event.metaKey;
    if (!typed || !(column.media || column.ref)) return;
    event.preventDefault();
    askRecord(key, column, column.ref ? event.key : "");
  };

  const pendingCount = Object.keys(changes).length + Object.values(files).filter((f) => Object.keys(f).length).length;

  const save = async () => {
    setBusy(true);
    setNotice("");
    const failed = new Set<string>();
    const created = new Map<string, string>();
    try {
      const changedRows = Object.keys(changes);
      if (changedRows.length > 0) {
        const response = await apiFetch<Batch<Row>>(`${base}/batch-update`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows: changedRows.map((key) => ({ pk: key, values: changedValues(columns, changes[key]) })) }) });
        for (const result of response.results) {
          const key = changedRows[result.index];
          if (!result.ok) failed.add(key);
        }
      }
      for (const [key, chosen] of Object.entries(files)) {
        const target = key;
        for (const [column, list] of Object.entries(chosen)) {
          if (!columns.some((c) => c.name === column)) continue;
          for (const file of list) {
            const form = new FormData();
            form.append("file", file, file.name);
            await apiForm(`${base}/${pathPk(target)}/files/${encodeURIComponent(column)}`, form);
          }
        }
      }
      setChanges(Object.fromEntries(Object.entries(changes).filter(([key]) => failed.has(key))));
      setFiles({});
      const savedChanges = Object.keys(changes).filter((key) => !failed.has(key)).length;
      setNotice(`Saved ${created.size} new row(s) and ${savedChanges} changed row(s).${failed.size ? ` ${failed.size} not saved.` : ""}`);
      setReload((value) => value + 1);
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : "The changes could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const imports = useTableImport({
    database,
    base,
    table,
    onDone: () => setReload((value) => value + 1),
    onNotice: setNotice,
    setBusy,
  });
  const { addRows, dialog: importDialog } = imports;

  const removeRows = async (keys: string[]) => {
    setAsking(false);
    setBusy(true);
    try {
      for (const key of keys) await apiFetch(`${base}/${pathPk(key)}`, { method: "DELETE" });
      setNotice(`Deleted ${keys.length} row(s).`);
      setPicked(new Set());
      setReload((value) => value + 1);
    } catch (failure) {
      setNotice(failure instanceof Error ? failure.message : "The rows could not be deleted.");
    } finally {
      setBusy(false);
    }
  };

  const changed = pendingCount;
  const pictures = columns.find((column) => column.media);

  const cell = (key: string, row: Row | null, column: ColumnInfo) => {
    const value = storedValue(key, row, column);
    const chosen = files[key]?.[column.name];
    const legacy = column.media && value.startsWith("data:") ? value : null;
    return (
      <td key={column.name} style={{ padding: 0, border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", verticalAlign: "middle", minWidth: column.media ? 200 : 120, height: column.media ? 88 : undefined, position: "relative" }}>
        {column.media ? (
          // A file cell is not a text box: a click or a key press opens the file chooser, and the files show below.
          <div
            role="button"
            tabIndex={canEdit ? 0 : -1}
            aria-label={`Row ${key}, ${column.name}: choose ${column.media.kind ?? "image"} files`}
            onClick={() => { if (canEdit) askRecord(key, column, ""); }}
            onKeyDown={(event) => { if (canEdit && (event.key === "Enter" || (event.key.length === 1 && !event.ctrlKey && !event.metaKey))) { event.preventDefault(); askRecord(key, column, ""); } }}
            style={{ position: "absolute", inset: 0, zIndex: 0, cursor: canEdit ? "pointer" : "default", outline: "none" }}
          />
        ) : column.type === "json" ? (
          // A json cell is edited in place, as text, with no dialog; the text is parsed when the rows are saved.
          <div style={{ padding: 4, minWidth: 160 }}>
            <JsonEditor
              label={`Row ${key}, ${column.name}`}
              value={shown(key, row, column)}
              disabled={!canEdit}
              onChange={(text) => setChange(key, column.name, text)}
            />
          </div>
        ) : (
          <input
            aria-label={`Row ${key}, ${column.name}`}
            value={shown(key, row, column)}
            readOnly={!canEdit || Boolean(column.ref)}
            title={column.ref && canEdit ? "Click to choose a record" : undefined}
            onChange={(event) => setChange(key, column.name, event.target.value)}
            onKeyDown={(event) => onKeyDown(event, key, column)}
            onClick={() => { if (canEdit && column.ref && !column.readonly) askRecord(key, column, ""); }}
            style={{ width: "100%", minWidth: 120, boxSizing: "border-box", padding: "6px 8px", background: "transparent", color: "inherit", border: 0, cursor: column.ref && canEdit ? "pointer" : undefined, textDecoration: column.ref && canEdit ? "underline dotted" : undefined }}
          />
        )}
        {column.media ? (
          <div style={{ position: "relative", zIndex: 1, pointerEvents: "none", display: "flex", alignItems: "center", justifyContent: "center", minHeight: 96, padding: 4 }}>
            {legacy ? <MediaView kind={column.media?.kind ?? "image"} src={legacy} name={column.name} /> : null}
            {!legacy && !chosen?.length ? <CellFiles api={api} table={table.name} pk={pathPk(key)} column={column.name} /> : null}
          </div>
        ) : null}
      </td>
    );
  };

  return (
    <section aria-label={`Table: ${table.label}`} className="stack" style={{ minWidth: 0, maxWidth: "100%" }}>
      {choosing && pick ? (
        <div role="status" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span>Choose a row of {table.name} for {pick.active?.origin.table}.{pick.active?.origin.column}: click the row.</span>
          <Button type="button" size="sm" variant="secondary" style={CONTROL} onClick={pick.cancel}>Cancel</Button>
        </div>
      ) : null}
      <div className="sn-toolbar" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", maxWidth: "100%", minWidth: 0 }}>
        <form role="search" onSubmit={(event) => event.preventDefault()} style={{ display: "flex", gap: 8, alignItems: "center", flex: "1 1 240px", minWidth: 0 }}>
          <TextBox
            type="search"
            name="q"
            aria-label={crudTr("search")}
            placeholder="Words or column:value"
            value={query}
            onChange={(event) => { setQuery(event.target.value); setOffset(0); }}
            style={{ ...CONTROL, flex: 1, minWidth: 0 }}
          />
        </form>
        {canEdit ? <Button type="button" size="md" variant="secondary" style={CONTROL} onClick={() => folderInput.current?.click()} disabled={busy}>Add rows</Button> : null}
        <ColumnsMenu label={crudTr("columns")} columns={[...table.pk, ...allColumns.map((column) => column.name)].map((name) => ({ key: name, label: name }))} shown={new Set([...visibleKeys, ...columns.map((column) => column.name)])} onToggle={(name, on) => setHidden((current) => { const next = new Set(current); if (on) next.delete(name); else next.add(name); return next; })} buttonStyle={CONTROL} />
        <input ref={folderInput} type="file" {...{ webkitdirectory: "" }} multiple onChange={addRows} style={{ display: "none" }} />
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "nowrap" }}>
        <SelectAllBar keys={page.rows.map((row) => rawPk(table, row))} picked={picked} onPicked={(next) => setPicked(new Set([...next].map(String)))} label={galleryTr("select_all")} />
        {picked.size > 0 ? <Button type="button" size="sm" variant="danger" style={{ flex: "none", whiteSpace: "nowrap" }} onClick={() => setAsking(true)}>{galleryTr("delete_selected", { count: picked.size })}</Button> : null}
        {changed > 0 ? <Button type="button" size="md" variant="primary" style={CONTROL} onClick={save} disabled={busy}>{`Save ${changed} change(s)`}</Button> : null}
        <span style={{ flex: 1 }} />
        <PageBar paging={{ pageSize, offset, setOffset, setPageSize: (size) => { setPageSize(size); setOffset(0); } }} total={page.total} label={table.label} />
      </div>
      {notice && <p aria-live="polite" style={{ margin: 0 }}>{notice}</p>}
      {importDialog}
      {recordRow ? <RecordDialog api={api} table={table} row={recordRow} onDone={() => { setRecordRow(null); setReload((value) => value + 1); }} onClose={() => setRecordRow(null)} onPickRef={(column, pending) => pickFromDialog(recordRow, column, pending)} /> : null}
      {error && <p role="alert" style={{ margin: 0 }}>{error}</p>}
      {cellDialog && cellDialog.column.media && (
        <FileCellDialog
          kind={cellDialog.column.media.kind ?? "image"}
          accept={cellDialog.column.media.accept}
          onClose={() => setCellDialog(null)}
          onPick={(list) => { addFiles(cellDialog.key, cellDialog.column.name, list); setCellDialog(null); }}
        />
      )}
      {cellDialog && cellDialog.column.ref && (
        <RefCellDialog
          key={refApi}
          api={refApi}
          table={cellDialog.column.ref.table}
          label={cellDialog.column.ref.label}
          keyColumn={cellDialog.column.ref.key ?? "id"}
          first={cellDialog.first}
          onClose={() => setCellDialog(null)}
          onPick={(key, text) => {
            setChange(cellDialog.key, cellDialog.column.name, key);
            setRefTexts((current) => ({ ...current, [`${cellDialog.key}:${cellDialog.column.name}`]: text }));
            setCellDialog(null);
          }}
        />
      )}
      <ConfirmModal open={asking} message={`Delete ${picked.size} row(s)? This cannot be undone.`} confirmLabel="Delete" cancelLabel="Cancel" onConfirm={() => void removeRows([...picked])} onCancel={() => setAsking(false)} />
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th scope="col" aria-label="Select" style={{ width: 44, padding: "6px 4px", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }} />
              {visibleKeys.map((name) => <th key={name} scope="col" style={{ textAlign: "left", minWidth: 56, fontSize: 13, whiteSpace: "nowrap", padding: "6px 8px", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }}>{name}</th>)}
              {columns.map((column) => <th key={column.name} scope="col" style={{ textAlign: "left", fontSize: 13, whiteSpace: "nowrap", padding: "6px 8px", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }}>{column.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {page.rows.map((row) => {
              const key = rawPk(table, row);
              return (
                <tr key={pkOf(table, row)} onDoubleClick={(event) => { if (!(event.target as HTMLElement).closest("input, button, audio, video, a, [title]")) setRecordRow(row); }} onClick={(event) => { if (choosing && !(event.target as HTMLElement).closest("input, button, audio, video, a")) pick?.pick(String(row[choosing.keyColumn]), String(row[choosing.labelColumn] ?? row[choosing.keyColumn])); }} style={{ background: changes[key] ? "color-mix(in srgb, var(--line) 6%, transparent)" : undefined }}>
                  <td style={{ border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", textAlign: "center" }}><input type="checkbox" aria-label={`Select row ${key}`} checked={picked.has(key)} onChange={(event) => setPicked((current) => { const next = new Set(current); if (event.target.checked) next.add(key); else next.delete(key); return next; })} /></td>
                  {visibleKeys.map((name) => <td key={name} style={{ padding: "6px 8px", minWidth: 56, border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)" }}>{tableCell(table, columns, row, name)}</td>)}
                  {columns.map((column) => cell(key, row, column))}
                </tr>
              );
            })}
            {!loading && page.rows.length === 0 && <tr><td colSpan={columns.length + visibleKeys.length + 1} className="muted">No rows.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
