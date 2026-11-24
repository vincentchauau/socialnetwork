"use client";

import { useState } from "react";

import CrudRowForm from "@sn/compounds/CrudRowForm";
import { type ColumnInfo, type Draft, type Row, type TableInfo, valuesOf } from "@sn/compounds/crudModel";

import { errorMessage } from "../errors";

const empty = (value: unknown): boolean => value === null || value === undefined || value === "";

function same(column: ColumnInfo, before: unknown, after: unknown): boolean {
  if (empty(before) || empty(after)) return empty(before) && empty(after);
  if (column.type === "datetime") return new Date(String(before)).getTime() === new Date(String(after)).getTime();
  return String(before) === String(after);
}

interface Props {
  table: TableInfo;
  /** The row as it is now. */
  row: Row;
  /** Does what the form asked for, given only the columns that changed; a rejection says why not (its words are shown in the form). */
  onSave: (changed: Row) => Promise<void>;
  onClose: () => void;
}

/** The "Edit row" form of the Table pane over a row of the chat (a room, a member, a message): it saves only what was changed, and shows the server's reason when it says no. */
export default function RowDialog({ table, row, onSave, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(draft: Draft) {
    const built = valuesOf(table, draft, true);
    if ("error" in built) return setError(built.error);
    const changed: Row = {};
    for (const column of table.columns) {
      if (column.name in built.values && !same(column, row[column.name], built.values[column.name])) changed[column.name] = built.values[column.name];
    }
    if (Object.keys(changed).length === 0) return onClose();
    setBusy(true);
    setError(null);
    try {
      await onSave(changed);
      onClose();
    } catch (caught) {
      setError(errorMessage(caught));
      setBusy(false);
    }
  }

  return <CrudRowForm table={table} row={row} busy={busy} error={error} onSubmit={(draft) => void submit(draft)} onCancel={onClose} />;
}
