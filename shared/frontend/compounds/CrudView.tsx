"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../api";
import Alert from "../elements/Alert";
import Button from "../elements/Button";
import TextBox from "../elements/TextBox";
import { ConfirmModal } from "./Dialogs";
import { UploadDialog } from "./FileTools";
import CrudRowForm from "./CrudRowForm";
import DataTable, { type Column, type Sort } from "./DataTable";
import { ColumnsMenu, Pager, SelectAllBar, CONTROL } from "./TableFooter";
import { NOWRAP_STYLE } from "./CellView";
import { useRecordList } from "./useRecordList";
import { PAGE_SIZES, PageSizeSelect, SearchBox, TermChips, useSearchTerms } from "./InputBox";
import { galleryTr } from "./galleryModel";
import { CellView, defaultShown } from "./CellView";
import { type Draft, type Labels, type Row, type TableInfo, crudTr, detailText, draftOf, isLocked, pkOf, valuesOf } from "./crudModel";
import CheckBox from "../elements/CheckBox";
import { MediaField } from "./FileTools";

export { crudTr, detailText, pkOf, valuesOf };
export type { ColumnInfo, ColumnType, Draft, Row, TableInfo } from "./crudModel";

export interface CrudViewProps {
  /** The admin base of one module, e.g. "/api/market/records". */
  api: string;
  table: TableInfo;
  /** The letters R, C, U, D of what the person may do with this table (from `/records/tables`). Absent: what the table's mode allows. */
  /** How a row is changed: `dialog` (default): the form of the row in a dialog, for Edit and Add row alike; `inline`: the cells of the row turn into boxes in place, and Add row opens a line of boxes above the table. */
  editMode?: "dialog" | "inline";
}

const COLUMNS_KEY = "sn_cols2_";
/** One size for every control of the toolbar (search box and buttons) so they line up. */

/** The order the server is asked for, as text (`key`, `-key`, or none) and as the sort the table shows. */
function sortState(order: string): Sort {
  if (!order) return null;
  return order.startsWith("-") ? { key: order.slice(1), direction: "desc" } : { key: order, direction: "asc" };
}

function sortText(next: Sort): string {
  if (!next) return "";
  return next.direction === "desc" ? `-${next.key}` : next.key;
}

function storedColumns(key: string): string[] | null {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(key) ?? "null");
    return Array.isArray(parsed) ? parsed.filter((name): name is string => typeof name === "string") : null;
  } catch {
    return null;
  }
}

/** One box of a row changed in place: a check box for a yes/no column, else a text box named after the column. */
function InlineBox({ column, draft, onChange }: { column: TableInfo["columns"][number]; draft: Draft; onChange: (next: Draft) => void }) {
  if (column.type === "bool") {
    return <CheckBox label={column.name} checked={Boolean(draft[column.name])} onChange={(checked) => onChange({ ...draft, [column.name]: checked })} />;
  }
  return <TextBox aria-label={column.name} placeholder={column.name} value={String(draft[column.name] ?? "")} onChange={(event) => onChange({ ...draft, [column.name]: event.target.value })} style={{ minWidth: 80 }} />;
}

/**
 * The data table of one table of a module: a real table (one row per record, technical columns hidden until the "Columns" menu shows them,
 * dates, flags, json, empty values and pictures written the way a person reads them), a search box, a footer with the range and previous/next,
 * and Add / Edit (a dialog) / Delete (asks first) as far as its table allows.
 */
export default function CrudView({ api, table, editMode = "dialog" }: CrudViewProps) {
  const inlineMode = editMode === "inline";
  const [inlineKey, setInlineKey] = useState<string | null>(null); // the row being changed in place
  const [adding, setAdding] = useState(false);
  const [inlineDraft, setInlineDraft] = useState<Draft>({});
  const [offset, setOffset] = useState(0);
  const searchTerms = useSearchTerms(useCallback(() => setOffset(0), []));
  const search = searchTerms.text;
  const [form, setForm] = useState<{ row: Row | null } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [sort, setSort] = useState(""); // a column, `-column` for the other way round, or none
  const PAGE_SIZE = pageSize;
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [uploading, setUploading] = useState(false);
  const [stamps, setStamps] = useState<Record<string, number>>({});
  const [chosen, setChosen] = useState<string[] | null>(null);
  const base = `${api}/${encodeURIComponent(table.name)}`;
  const { rows, labels, total, loading, loadError, setLoadError, picked, setPicked, bulkAsking, setBulkAsking, reload, deleteKeys, removePicked } = useRecordList({
    base,
    query: new URLSearchParams({ q: search, offset: String(offset), limit: String(PAGE_SIZE), ...(sort ? { sort } : {}) }).toString(),
  });
  const canWrite = table.writable;
  const canCreate = canWrite;
  const canEdit = table.writable;
  const canDelete = table.writable;

  useEffect(() => {
    searchTerms.clear();
    setOffset(0);
    setSort("");
    setForm(null);
    setDeleting(null);
    setUploading(false);
    setChosen(storedColumns(COLUMNS_KEY + base));
  }, [base]);

  const closeForm = useCallback(() => setForm(null), []);

  const shown = useMemo(() => new Set(chosen ?? defaultShown(table)), [chosen, table]);
  const visibleColumns = table.columns.filter((column) => shown.has(column.name));

  function toggleColumn(name: string, on: boolean) {
    const next = table.columns.map((column) => column.name).filter((candidate) => (candidate === name ? on : shown.has(candidate)));
    setChosen(next);
    try {
      window.localStorage.setItem(COLUMNS_KEY + base, JSON.stringify(next));
    } catch {
      // not remembered: fine
    }
  }

  async function save(draft: Draft, row?: Row | null, done?: () => void) {
    const editing = row === undefined ? (form?.row ?? null) : row;
    const built = valuesOf(table, draft, editing !== null);
    if ("error" in built) {
      setFormError(built.error);
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const path = editing ? `${base}/${pkOf(table, editing)}` : base;
      await apiFetch(path, { method: editing ? "PATCH" : "POST", body: JSON.stringify({ values: built.values }) });
      setForm(null);
      done?.();
      reload();
    } catch (error) {
      setFormError(detailText(error));
    } finally {
      setBusy(false);
    }
  }

  function startInlineEdit(row: Row) {
    setFormError(null);
    setAdding(false);
    setInlineKey(pkOf(table, row));
    setInlineDraft(draftOf(table, row));
  }

  function startInlineAdd() {
    setFormError(null);
    setInlineKey(null);
    setAdding(true);
    setInlineDraft(draftOf(table, null));
  }

  function stopInline() {
    setInlineKey(null);
    setAdding(false);
  }

  function mediaReplaced(row: Row) {
    setStamps((previous) => ({ ...previous, [pkOf(table, row)]: Date.now() }));
    reload();
  }

  async function remove() {
    const row = deleting;
    setDeleting(null);
    if (!row) return;
    if (await deleteKeys([pkOf(table, row)])) {
      if (rows.length === 1 && offset > 0) setOffset(Math.max(0, offset - PAGE_SIZE));
      else reload();
    }
  }

  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);
  const columns: Column<Row>[] = visibleColumns.map((column) => ({
    key: column.name,
    label: column.name,
    narrow: table.pk.includes(column.name) || column.name.endsWith("_id"),
    // The rows are sorted by the server: a sortable column only needs a value to show its arrows (the order itself is not computed here).
    sortValue: !column.secret && column.type !== "json" && column.type !== "bytes" ? () => "" : undefined,
    render: (row) =>
      inlineKey !== null && inlineKey === pkOf(table, row) && column.media?.replace ? (
        <MediaField table={table} column={column} row={row} stamp={stamps[pkOf(table, row)]} onReplaced={() => mediaReplaced(row)} />
      ) : inlineKey !== null && inlineKey === pkOf(table, row) && !isLocked(table, column, true) && !column.media ? (
        <InlineBox column={column} draft={inlineDraft} onChange={setInlineDraft} />
      ) : (
        <CellView column={column} value={row[column.name]} labels={labels[column.name]} table={table} row={row} stamp={stamps[pkOf(table, row)]} />
      ),
  }));
  const uploadAccept = table.columns.find((column) => column.media?.accept)?.media?.accept;
  const hasActions = canEdit || canDelete;

  return (
    <section aria-label={table.label} className="stack">
      <div className="sn-toolbar" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <SearchBox search={searchTerms} controlStyle={CONTROL} />
        <ColumnsMenu label={crudTr("columns")} columns={table.columns.map((column) => ({ key: column.name, label: column.name }))} shown={shown} onToggle={toggleColumn} suspended={form !== null} buttonStyle={CONTROL} />
        {table.create_via && canCreate ? (
          <Button type="button" size="md" variant="secondary" style={CONTROL} onClick={() => setUploading(true)}>{crudTr("create")}</Button>
        ) : canCreate ? (
          <Button type="button" size="md" variant="secondary" style={CONTROL} onClick={() => (inlineMode ? startInlineAdd() : (setFormError(null), setForm({ row: null })))}>{crudTr("create")}</Button>
        ) : null}
      </div>
      <PageSizeSelect value={pageSize} onChange={(size) => { setPageSize(size); setOffset(0); }} />
      {total > pageSize ? <Pager
        label={table.label}
        from={from}
        to={to}
        total={total}
        disabled={loading}
        rangeText={crudTr("page", { from, to, total })}
        prevLabel={crudTr("prev")}
        nextLabel={crudTr("next")}
        onPrev={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        onNext={() => setOffset(offset + PAGE_SIZE)}
      /> : null}
      <TermChips search={searchTerms} total={total} ready={!loading && !loadError} />
      {!canWrite && !canEdit ? <p className="muted" style={{ margin: 0 }}>{crudTr("read_only_table")}</p> : null}
      {form && (form.row ? canEdit : canCreate) ? (
        <CrudRowForm api={api} key={form.row ? pkOf(table, form.row) : "new"} table={table} row={form.row} labels={labels} busy={busy} error={formError} onSubmit={(draft) => void save(draft)} onCancel={closeForm} stamp={form.row ? stamps[pkOf(table, form.row)] : undefined} onMediaReplaced={() => form.row && mediaReplaced(form.row)} />
      ) : null}
      {inlineMode && adding && canCreate ? (
        <form
          aria-label={crudTr("create")}
          onSubmit={(event) => {
            event.preventDefault();
            void save(inlineDraft, null, stopInline);
          }}
          style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", padding: 8, borderRadius: 8, background: "color-mix(in srgb, var(--line) 8%, transparent)" }}
        >
          {table.columns.filter((column) => !isLocked(table, column, false) && !column.media).map((column) => (
            <InlineBox key={column.name} column={column} draft={inlineDraft} onChange={setInlineDraft} />
          ))}
          <Button type="submit" size="sm" disabled={busy}>{crudTr("create")}</Button>
          <Button type="button" size="sm" variant="secondary" onClick={stopInline}>{crudTr("cancel")}</Button>
        </form>
      ) : null}
      {inlineMode && formError ? <Alert>{formError}</Alert> : null}
      {uploading && table.create_via ? (
        <UploadDialog path={table.create_via} title={table.create_label ?? crudTr("upload_title")} accept={uploadAccept} onUploaded={reload} onClose={() => setUploading(false)} />
      ) : null}
      {loadError ? <Alert>{loadError}</Alert> : null}
      {loading ? <p role="status" style={{ margin: 0 }}>{crudTr("loading")}</p> : null}
      {canDelete ? (
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <SelectAllBar keys={rows.map((row) => pkOf(table, row))} picked={picked} onPicked={(next) => setPicked(new Set([...next].map(String)))} label={galleryTr("select_all")} />
          {picked.size > 0 ? <Button type="button" size="sm" variant="danger" style={{ flex: "none", whiteSpace: "nowrap" }} onClick={() => setBulkAsking(true)}>{galleryTr("delete_selected", { count: picked.size })}</Button> : null}
        </div>
      ) : null}
      <DataTable
        label={crudTr("rows", { table: table.label })}
        columns={columns}
        rows={rows}
        rowKey={(row) => pkOf(table, row)}
        pickable={() => canDelete}
        picked={picked}
        headerSelect={false}
        sort={sortState(sort)}
        onSort={(next) => { setOffset(0); setSort(sortText(next)); }}
        onPicked={setPicked}
        rowLabel={(row) => String(pkOf(table, row))}
        empty={loading || loadError ? "" : crudTr("empty")}
        actions={
          hasActions
            ? (row) => (
                inlineKey !== null && inlineKey === pkOf(table, row) ? (
                <>
                  <Button size="sm" style={NOWRAP_STYLE} disabled={busy} onClick={() => void save(inlineDraft, row, stopInline)}>{crudTr("save")}</Button>
                  <Button size="sm" variant="secondary" style={NOWRAP_STYLE} onClick={stopInline}>{crudTr("cancel")}</Button>
                </>
              ) : (
                <>
                  {canEdit ? (
                    <Button size="sm" variant="secondary" style={NOWRAP_STYLE} aria-label={`${crudTr("edit")} ${pkOf(table, row)}`} title={crudTr("edit")} onClick={() => (inlineMode ? startInlineEdit(row) : (setFormError(null), setForm({ row })))}>{crudTr("edit")}</Button>
                  ) : null}
                  {canDelete ? (
                    <Button size="sm" variant="danger" style={NOWRAP_STYLE} aria-label={`${crudTr("delete")} ${pkOf(table, row)}`} title={crudTr("delete")} onClick={() => setDeleting(row)}>{crudTr("delete")}</Button>
                  ) : null}
                </>
              ))
            : undefined
        }
      />
      <ConfirmModal open={bulkAsking} message={crudTr("confirm_delete_picked", { count: picked.size })} confirmLabel={crudTr("delete")} cancelLabel={crudTr("cancel")} onConfirm={() => void removePicked()} onCancel={() => setBulkAsking(false)} />
      <ConfirmModal open={deleting !== null} message={crudTr("confirm_delete")} confirmLabel={crudTr("delete")} cancelLabel={crudTr("cancel")} onConfirm={remove} onCancel={() => setDeleting(null)} />
    </section>
  );
}
