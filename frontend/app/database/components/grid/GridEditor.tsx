"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { apiFetch } from "@sn/api";
import Button from "@sn/elements/Button";
import GalleryView, { CONTROL } from "@sn/compounds/GalleryView";
import { autoGalleryConfig } from "@sn/compounds/galleryModel";
import type { ColumnInfo, Row, TableInfo } from "@sn/compounds/crudModel";

import FieldDialog from "../record/FieldDialog";
import CellFiles from "@sn/compounds/RecordFiles";
import { changedValues, pathPk, rawPk, tableColumns } from "@sn/compounds/recordModel";
import { useTableImport } from "../table/tableImport";
import { useDatabaseSelection } from "../../selection";
import { pickFiles } from "@sn/compounds/Dialogs";
import { apiForm } from "@sn/api";
import { useRefPick } from "../refs/refPick";
import RecordDialog from "../record/RecordDialog";

interface Editing {
  row: Row;
  column: ColumnInfo;
}

/** The Grid of the Database tab: the cards of the table as before, with a double click on a field to change it, and the Excel and
 * folder imports of the table. */
export default function GridEditor({ api, table }: { api: string; table: TableInfo & { database?: string } }) {
  const [editing, setEditing] = useState<Editing | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const folderInput = useRef<HTMLInputElement>(null);
  const reloadRef = useRef<() => void>(() => undefined);
  const [recordRow, setRecordRow] = useState<Row | null>(null);
  const selection = useDatabaseSelection();
  const pick = useRefPick();

  // Back from a record picker: the record chosen for a reference field is saved into its row, then the cards are shown again.
  useEffect(() => {
    if (!pick) return;
    const result = pick.takeResult(table.database ?? "", table.name);
    if (!result) return;
    const column = table.columns.find((c) => c.name === result.origin.column);
    if (!column) return;
    const row = { [table.pk[0]]: result.origin.key } as Row;
    saveText(api, table, row, column, result.value)
      .then(() => reloadRef.current())
      .catch(() => reloadRef.current());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once, when the grid is shown again
  }, []);

  // A reference field asks for its record in the Table tab: the referenced table is shown, in the app that owns it.
  const askRecord = (row: Row, column: ColumnInfo) => {
    if (column.media) {
      const uploadAll = async (list: File[]) => {
        for (const file of list) {
          const form = new FormData();
          form.append("file", file, file.name);
          await apiForm(`${api}/${encodeURIComponent(table.name)}/${pathPk(rawPk(table, row))}/files/${encodeURIComponent(column.name)}`, form);
        }
        reloadRef.current();
      };
      pickFiles(column.media.kind ?? "image", column.media.accept, (list) => { void uploadAll(list); }, () => undefined);
      return;
    }
    if (!pick || !column.ref) return setEditing({ row, column });
    const owner = selection?.tables.find((t) => t.name === column.ref?.table)?.database ?? (table.database ?? "");
    pick.start(
      { database: table.database ?? "", table: table.name, key: rawPk(table, row), column: column.name },
      { database: owner, table: column.ref.table, keyColumn: column.ref.key ?? "id", labelColumn: column.ref.label },
      { changes: {}, files: {}, refTexts: {} },
    );
  };
  const editable = table.writable;
  // The Columns menu lists every column of the table (the id, the title and the picture too), all shown at first, as in the Table.
  const galleryConfig = useMemo(() => {
    const base = autoGalleryConfig(table);
    const meta = table.columns.filter((c) => !c.secret && c.type !== "bytes").map((c) => c.name);
    return { ...base, meta, allColumns: true };
  }, [table]);
  const base = `${api}/${encodeURIComponent(table.name)}`;
  const { addRows, dialog } = useTableImport({ database: table.database ?? "", base, table, onDone: () => reloadRef.current(), onNotice: setNotice, setBusy });
  const addButton = editable ? (
    <>
      <Button type="button" size="md" variant="secondary" style={CONTROL} onClick={() => folderInput.current?.click()} disabled={busy}>Add rows</Button>
      <input ref={folderInput} type="file" {...{ webkitdirectory: "" }} multiple onChange={addRows} style={{ display: "none" }} />
    </>
  ) : undefined;
  return (
    <GalleryView
      api={api}
      table={table.name}
      config={galleryConfig}
      onField={editable ? (row, column) => askRecord(row, column) : undefined}
      onFieldSave={editable ? (row, column, text) => saveText(api, table, row, column, text) : undefined}
      cardButtons={false}
      selectable
      hideAdd
      toolbarStart={addButton}
      onOpen={(row) => setRecordRow(row)}
      renderThumb={(row, column) => <CardPicture api={api} table={table.name} pk={rawPk(table, row)} column={column.name} />}
      renderMedia={(row, column) => <CellFiles api={api} table={table.name} pk={pathPk(rawPk(table, row))} column={column.name} />}
      createSlot={(reload) => {
        reloadRef.current = reload;
        if (!notice && !dialog && !editing && !recordRow) return null; // nothing to show: no empty row above the toolbar
        return (
          <div style={{ display: "grid", gap: 8 }}>
            {notice ? <span role="status">{notice}</span> : null}
            {dialog}
            {recordRow ? <RecordDialog api={api} table={table} row={recordRow} onDone={() => { setRecordRow(null); reloadRef.current(); }} onClose={() => setRecordRow(null)} onPickRef={(column) => { setRecordRow(null); askRecord(recordRow, column); }} /> : null}
            {editing ? <FieldDialog api={api} table={table} row={editing.row} column={editing.column} onDone={() => { setEditing(null); reload(); }} onClose={() => setEditing(null)} /> : null}
          </div>
        );
      }}
    />
  );
}

/** Saves one text field of one row (the server checks it). Rejects with the reason when the row is not saved. */
async function saveText(api: string, table: TableInfo, row: Row, column: ColumnInfo, text: string): Promise<void> {
  const response = await apiFetch<{ results: { ok: boolean; error?: string }[] }>(`${api}/${encodeURIComponent(table.name)}/batch-update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows: [{ pk: rawPk(table, row), values: changedValues([column], { [column.name]: text }) }] }),
  });
  if (!response.results[0]?.ok) throw new Error(response.results[0]?.error ?? "Not saved");
}

/** The picture of a row for a card: its first picture file, or a plain frame when it has none. */
function CardPicture({ api, table, pk, column }: { api: string; table: string; pk: string; column: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const base = `${api}/${encodeURIComponent(table)}/${pk}/files/${encodeURIComponent(column)}`;
  useEffect(() => {
    let alive = true;
    apiFetch<{ files: { name: string; kind: string }[] }>(base)
      .then((response) => {
        const first = (Array.isArray(response?.files) ? response.files : []).find((file) => file.kind === "image");
        if (alive) setSrc(first ? `${base}/${encodeURIComponent(first.name)}` : null);
      })
      .catch(() => { if (alive) setSrc(null); });
    return () => { alive = false; };
  }, [base]);
  if (!src) return <span aria-hidden="true" style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", fontSize: 28, opacity: 0.3 }}>▢</span>;
  return <img src={src} alt="" loading="lazy" style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />;
}
