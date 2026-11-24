"use client";

import { type ChangeEvent, type ReactNode, useState } from "react";

import { apiFetch, apiForm } from "@sn/api";
import type { ColumnInfo, TableInfo } from "@sn/compounds/crudModel";

import { Dialog } from "@sn/compounds/Dialogs";

/** The Excel file of an import: `data.xlsx` at the top of the folder that was chosen. */
const EXCEL_NAME = "data.xlsx";

interface Pending {
  excel: File;
  files: File[];
  existing: number;
  fresh: number;
}

interface ImportResult {
  results: { index: number; status: string; id?: string | number }[];
  created: number;
  updated: number;
  skipped: number;
}

/** The files of one cell of one row, found in a folder laid out as `{database}/{table}/{column}/{row_id}/{file}`. */
export function filesOfCell(files: File[], database: string, table: string, column: string, rowId: string): File[] {
  return files.filter((file) => {
    const parts = (file.webkitRelativePath || file.name).split("/");
    for (let index = 0; index + 4 < parts.length; index += 1) {
      if (parts[index] === database && parts[index + 1] === table && parts[index + 2] === column && parts[index + 3] === rowId) return true;
    }
    return false;
  });
}

/** Adding rows from a folder: its `data.xlsx` makes the rows, its `{database}/{table}/{column}/{row_id}/` folders hold their files.
 * When some ids are already in the table the person chooses: overwrite them, or only add the new rows. */
export function useTableImport({ database, base, table, onDone, onNotice, setBusy }: {
  database: string; base: string; table: TableInfo; onDone: () => void; onNotice: (text: string) => void; setBusy: (busy: boolean) => void;
}) {
  const [pending, setPending] = useState<Pending | null>(null);

  const run = async (overwrite: boolean, job: Pending) => {
    setPending(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", job.excel, EXCEL_NAME);
      form.append("overwrite", overwrite ? "true" : "false");
      const imported = await apiForm<ImportResult>(`${base}/import`, form);
      const ids = imported.results.filter((r) => (r.status === "created" || r.status === "updated") && r.id !== undefined).map((r) => String(r.id));
      let uploaded = 0;
      let refused = 0;
      for (const column of table.columns.filter((c: ColumnInfo) => c.media)) {
        for (const id of ids) {
          for (const file of filesOfCell(job.files, database, table.name, column.name, id)) {
            const body = new FormData();
            body.append("file", file, file.name);
            try {
              await apiForm(`${base}/${encodeURIComponent(id)}/files/${encodeURIComponent(column.name)}`, body);
              uploaded += 1;
            } catch {
              refused += 1;
            }
          }
        }
      }
      onNotice(`Added ${imported.created} row(s), updated ${imported.updated}, skipped ${imported.skipped}; uploaded ${uploaded} file(s)${refused ? `, ${refused} refused` : ""}.`);
      onDone();
    } catch (failure) {
      onNotice(failure instanceof Error ? failure.message : "The rows could not be added.");
    } finally {
      setBusy(false);
    }
  };

  // A new empty row, when no folder with the Excel file was chosen: the row is made with no values and can be filled in later.
  const addEmptyRow = async () => {
    setBusy(true);
    try {
      await apiFetch(base, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ values: {} }) });
      onNotice("Added an empty row.");
      onDone();
    } catch (failure) {
      onNotice(failure instanceof Error ? failure.message : "The row could not be added.");
    } finally {
      setBusy(false);
    }
  };

  const addRows = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(event.target.files ?? []);
    event.target.value = "";
    const excel = chosen.find((file) => (file.webkitRelativePath || "").split("/").length === 2 && file.name === EXCEL_NAME);
    if (!excel) return addEmptyRow();
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", excel, EXCEL_NAME);
      const plan = await apiForm<{ new: number; existing: number }>(`${base}/import-plan`, form);
      const job = { excel, files: chosen, existing: plan.existing, fresh: plan.new };
      if (plan.existing === 0) await run(false, job);
      else setPending(job);
    } catch (failure) {
      onNotice(failure instanceof Error ? failure.message : "The folder could not be read.");
    } finally {
      setBusy(false);
    }
  };

  const dialog: ReactNode = pending ? (
    <Dialog label="Some rows are already there" onClose={() => setPending(null)}>
      <p style={{ margin: 0 }}>{pending.existing} row(s) have an id that is already in the table. {pending.fresh} row(s) are new.</p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => void run(true, pending)}>Overwrite the {pending.existing} existing</button>
        <button type="button" onClick={() => void run(false, pending)}>Only add the {pending.fresh} new</button>
        <button type="button" onClick={() => setPending(null)}>Cancel</button>
      </div>
    </Dialog>
  ) : null;

  return { addRows, dialog };
}
