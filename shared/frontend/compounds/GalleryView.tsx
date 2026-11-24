"use client";

import { type ReactNode, useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type Key, useMemo } from "react";
import { apiFetch, apiForm } from "../api";
import { pickLanguage, intlLocale } from "../lib/i18n";
import { useSession } from "../lib/useSession";
import { onRecordsChanged } from "../lib/recordsChanged";
import Alert from "../elements/Alert";
import Button from "../elements/Button";
import Select from "../elements/Select";
import { ConfirmModal } from "./Dialogs";
import CrudRowForm from "./CrudRowForm";
import { ColumnsMenu, PageBar, SelectAllBar, CONTROL } from "./TableFooter";
import { useRecordList } from "./useRecordList";
import { PageSizeSelect, SearchBox, TermChips, useSearchTerms } from "./InputBox";
import { UploadDialog, MediaView } from "./FileTools";
import { type Draft, type Labels, Row, TableInfo, crudTr, textOfValue, detailText, pkOf, valuesOf, type ColumnInfo, type MediaKind, fileName, humanize, mediaKind, mediaSrc } from "./crudModel";
import { DEFAULT_CARD_MIN_WIDTH, DEFAULT_PAGE_SIZE, type GalleryConfig, SUGGEST_LIMIT, galleryTr, loadGalleryTables, mergeLabels, pageParams, suggestValues, type GalleryAction, type GalleryActionContext, autoGalleryConfig } from "./galleryModel";
import { LINE_SOFT, SURFACE } from "../lib/theme";
import { KIND_ICON, NOWRAP_STYLE, CellView, hueOf } from "./CellView";
import { BORDER } from "./FileTools";
import { justifiedRows } from "./galleryModel";

export type { GalleryConfig } from "./galleryModel";

export interface GalleryViewProps {
  /** The base of one module's table API, e.g. "/api/video/data". */
  api: string;
  table: string;
  /** The letters R, C, U, D the person may use (from `/tables`). Absent: what the table's mode allows, like CrudView. */
  config: GalleryConfig;
  /** Content above the toolbar, owned by the app (e.g. a create form). It gets `reload` to refresh the cards after it created something. */
  createSlot?: (reload: () => void) => ReactNode;
  /** A field shown on a card was double clicked (the Database tab edits it in a dialog). Absent: the fields are only shown. */
  onField?: (row: Row, column: ColumnInfo) => void;
  /** A text field changed in place on its card (double click, type, Enter). Rejects with the reason when not saved. */
  onFieldSave?: (row: Row, column: ColumnInfo, text: string) => Promise<void>;
  /** Edit and Delete buttons on each card. Absent: shown as the table allows. */
  cardButtons?: boolean;
  /** Cards can be picked to delete them together. Absent: as the table and the config allow. */
  selectable?: boolean;
  /** Hides the built-in Add button (the app adds rows another way, e.g. from a folder). */
  hideAdd?: boolean;
  /** Controls placed in the toolbar before the Columns menu (the app's own, e.g. Add rows). */
  toolbarStart?: ReactNode;
  /** The picture at the top of a card, drawn by the app (e.g. the first file of the row). Absent: the picture of the column. */
  renderThumb?: (row: Row, column: ColumnInfo) => ReactNode;
  /** The media of a card, drawn by the app (its players). */
  renderMedia?: (row: Row, column: ColumnInfo) => ReactNode;
  /** A card was double clicked (not its controls): the app opens the record. */
  onOpen?: (row: Row) => void;
}

export { CONTROL } from "./TableFooter";

/** The chips of the filter columns: the values the column holds, the most common first (the groups route); a failed route shows none. */
function useChips(base: string, columns: string[], ready: boolean): Record<string, string[]> {
  const [chips, setChips] = useState<Record<string, string[]>>({});
  const key = columns.join("|");
  useEffect(() => {
    let cancelled = false;
    setChips({});
    if (!ready) return;
    for (const column of columns) {
      apiFetch<unknown>(`${base}/groups?${new URLSearchParams({ column, limit: String(SUGGEST_LIMIT) })}`)
        .then((answer) => {
          if (!cancelled) setChips((previous) => ({ ...previous, [column]: suggestValues(answer) }));
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, key, ready]);
  return chips;
}

/** The owner's label of a row (the response label, else "#<id>"); empty when the row has no owner. */
function ownerOf(row: Row, column: string, labels: Labels): string {
  const id = row[column];
  if (id === null || id === undefined || id === "") return "";
  return labels[column]?.[String(id)] ?? `#${String(id)}`;
}

/**
 * The page of one table as a grid of cards, built from the same table description and API as CrudView: search, filter chips, sort,
 * "Load more" (offset paging), Add (the shared form, or the upload dialog for a `create_via` table), Edit and Delete as far as `ops` allow.
 */
export default function GalleryView({ api: dataApi, table: tableName, config, createSlot, onField, onFieldSave, cardButtons = true, selectable, hideAdd, toolbarStart, renderThumb, renderMedia, onOpen }: GalleryViewProps) {
  const auth = useSession();
  // One address for everyone (/records): an admin sees every row, anyone else their own.
  const allUsers = auth.status === "signed-in" && auth.user.group === "admin";
  const api = dataApi;
  const sessionReady = auth.status !== "loading";
  const [pageSize, setPageSize] = useState(config.pageSize ?? DEFAULT_PAGE_SIZE);
  const [table, setTable] = useState<TableInfo | null>(null);
  const [missing, setMissing] = useState(false);
  const [sort, setSort] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const searchTerms = useSearchTerms(useCallback(() => setOffset(0), []));
  const search = searchTerms.text;
  const terms = searchTerms.terms;
  const [form, setForm] = useState<{ row: Row | null } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [uploading, setUploading] = useState(false);
  const [stamps, setStamps] = useState<Record<string, number>>({});
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const wantNext = useRef(false);
  const [selecting, setSelecting] = useState(false);
  const [metaChosen, setMetaChosen] = useState<string[] | null>(null);
  const base = `${api}/${encodeURIComponent(tableName)}`;
  const canWrite = table?.writable ?? false;
  const canCreate = canWrite;
  const canEdit = Boolean(table?.writable);
  const canDelete = Boolean(table?.writable);
  const filterColumns = config.filters ?? [];
  const chips = useChips(base, filterColumns, table !== null);
  const showOwner = allUsers && Boolean(config.ownerColumn);
  const list = useRecordList({
    base,
    query: pageParams({ search, offset, limit: pageSize, sort, filters }).toString(),
    append: offset > 0 && !config.paged, // a page replaces the cards; otherwise the next batch is added after them
    ready: table !== null,
  });
  const { rows, setRows, labels, total, loading, loadError, setLoadError, picked, setPicked, bulkAsking, setBulkAsking, deleteKeys } = list;

  useEffect(() => {
    let cancelled = false;
    setTable(null);
    setMissing(false);
    if (!sessionReady) return;
    loadGalleryTables(api).then((tables) => {
      if (cancelled) return;
      const found = tables.find((candidate) => candidate.name === tableName);
      setTable(found ?? null);
      setMissing(!found);
    });
    return () => {
      cancelled = true;
    };
  }, [api, tableName, sessionReady]);

  const reload = useCallback(() => {
    setOffset(0);
    list.reload();
  }, [list.reload]);

  useEffect(() => onRecordsChanged(tableName, reload), [tableName, reload]);

  useEffect(() => {
    if (!wantNext.current || loading || !table) return;
    const at = rows.findIndex((row) => pkOf(table, row) === previewKey);
    if (at >= 0 && rows[at + 1]) {
      wantNext.current = false;
      setPreviewKey(pkOf(table, rows[at + 1]));
    }
  }, [rows, loading, table, previewKey]);

  const more = rows.length < total && !config.paged;
  const sentinel = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = sentinel.current;
    if (!config.infiniteScroll || !node || !more || loading || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setOffset(rows.length);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [config.infiniteScroll, more, loading, rows.length]);

  async function save(draft: Draft, file?: File | null) {
    if (!table) return;
    if (file !== undefined && table.create_via) {
      if (!file) {
        setFormError(galleryTr("file_required"));
        return;
      }
      const body = new FormData();
      body.append("file", file);
      for (const name of table.create_fields ?? []) if (String(draft[name] ?? "") !== "") body.append(name, String(draft[name]));
      setBusy(true);
      setFormError(null);
      try {
        await apiForm(table.create_via, body);
        setForm(null);
        reload();
      } catch (error) {
        setFormError(detailText(error));
      } finally {
        setBusy(false);
      }
      return;
    }
    const editing = form?.row ?? null;
    const built = valuesOf(table, draft, editing !== null);
    if ("error" in built) {
      setFormError(built.error);
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await apiFetch(editing ? `${base}/${pkOf(table, editing)}` : base, { method: editing ? "PATCH" : "POST", body: JSON.stringify({ values: built.values }) });
      setForm(null);
      reload();
    } catch (error) {
      setFormError(detailText(error));
    } finally {
      setBusy(false);
    }
  }

  /** Renames a card in place: the title changes at once and goes back when the server refuses. */
  async function rename(row: Row, value: string) {
    const column = config.renameColumn;
    if (!table || !column) return;
    const key = pkOf(table, row);
    const previous = row[column];
    const patch = (next: unknown) => setRows((current) => current.map((item) => (pkOf(table, item) === key ? { ...item, [column]: next } : item)));
    patch(value);
    try {
      await apiFetch(`${base}/${key}`, { method: "PATCH", body: JSON.stringify({ values: { [column]: value } }) });
    } catch (error) {
      patch(previous);
      throw error;
    }
  }

  async function remove() {
    const row = deleting;
    setDeleting(null);
    if (!row || !table) return;
    if (await deleteKeys([pkOf(table, row)])) reload();
  }

  function toggleSelected(key: string, on: boolean) {
    setPicked((previous) => {
      const next = new Set(previous);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  async function removeSelected() {
    setBulkAsking(false);
    const keys = [...picked];
    setPicked(new Set());
    await deleteKeys(keys);
    reload();
  }

  function toggleFilter(column: string, value: string) {
    setOffset(0);
    setFilters((previous) => ({ ...previous, [column]: previous[column] === value ? "" : value }));
  }

  if (missing) return <Alert>{galleryTr("load_failed")}</Alert>;
  if (!table) return <p role="status" style={{ margin: 0 }}>{crudTr("loading")}</p>;

  const uploadAccept = table.columns.find((column) => column.media?.accept)?.media?.accept;
  const uploadForm = table.create_fields !== undefined;
  const canUpload = !config.addHref && Boolean(table.create_via);
  const addLabel = table.create_label ?? galleryTr("add");
  const editingRow = form?.row ?? null;
  const columns = config.cardMinWidth ?? DEFAULT_CARD_MIN_WIDTH;
  const actionContext = { reload, api, table: tableName };
  const addText = pickLanguage(config.addLabel ?? galleryTr("add"));
  const pickable = selectable ?? (canDelete && table.writable && !config.simple && (!config.friendly || selecting));
  const canRename = Boolean(config.renameColumn) && Boolean(canEdit);
  const factColumns = table.columns.filter((column) => !column.secret && column.type !== "bytes" && column.name !== config.title && column.name !== config.image && column.name !== config.badge && column.name !== config.body).map((column) => column.name);
  const metaChoices = config.allColumns ? table.columns.filter((column) => !column.secret && column.type !== "bytes").map((column) => column.name) : factColumns;
  const metaShown = metaChosen ?? config.meta ?? [];
  // The menu lists `metaChoices`: a toggle keeps every choice of that list, title and cover included when all columns are shown.
  const toggleMeta = (name: string, on: boolean) => setMetaChosen(metaChoices.filter((candidate) => (candidate === name ? on : metaShown.includes(candidate))));
  const shownMeta = metaChosen ? { ...config, meta: metaChosen } : config;
  const shownConfig = config.allColumns ? { ...shownMeta, hideTitle: !metaShown.includes(config.title ?? ""), hideImage: !metaShown.includes(config.image ?? "") } : shownMeta;
  const previewAt = rows.findIndex((row) => pkOf(table, row) === previewKey);
  const previewNav = previewAt < 0 ? undefined : { index: previewAt + 1, total, hasPrev: previewAt > 0, hasNext: config.paged ? previewAt + 1 < rows.length : previewAt + 1 < total };
  const step = (direction: -1 | 1) => {
    const next = rows[previewAt + direction];
    if (previewAt < 0) return;
    if (next) setPreviewKey(pkOf(table, next));
    else if (direction === 1 && rows.length < total) {
      wantNext.current = true;
      setOffset(rows.length);
    }
  };

  return (
    <section aria-label={table.label} className="stack" style={{ minWidth: 0, maxWidth: "100%" }}>
      {createSlot ? createSlot(reload) : null}
      <div className="sn-toolbar" style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", maxWidth: "100%", minWidth: 0 }}>
        <SearchBox search={searchTerms} controlStyle={CONTROL} placeholder={config.searchPlaceholder ? pickLanguage(config.searchPlaceholder) : undefined} />
        {toolbarStart}
        {metaChoices.length > 0 && !config.simple && !config.friendly ? <ColumnsMenu label={crudTr("columns")} columns={metaChoices.map((name) => ({ key: name, label: name }))} shown={new Set(metaShown)} onToggle={toggleMeta} buttonStyle={CONTROL} /> : null}
        {config.sort && config.sort.length > 0 ? (
          <Select aria-label={galleryTr("sort")} value={sort} onChange={(event) => { setOffset(0); setSort(event.target.value); }} style={{ ...CONTROL, padding: "0 8px" }}>
            <option value="">{galleryTr("sort")}: {galleryTr("sort_default")}</option>
            {config.sort.map((option) => <option key={option.column} value={option.column}>{pickLanguage(option.label)}</option>)}
          </Select>
        ) : null}
        {config.friendly && canDelete && table.writable && !config.simple ? (
          <Button type="button" size="md" variant="secondary" style={CONTROL} aria-pressed={selecting} onClick={() => { setSelecting(!selecting); setPicked(new Set()); }}>{selecting ? galleryTr("done") : galleryTr("select_mode")}</Button>
        ) : null}
        {config.hideAdd ? null : config.addHref ? (
          <a href={config.addHref} style={{ ...CONTROL, display: "inline-flex", alignItems: "center", textDecoration: "none", border: "1px solid color-mix(in srgb, var(--line) 30%, transparent)", borderRadius: 6, background: "var(--solid-2)", color: "var(--line)" }}>{pickLanguage(config.addLabel ?? galleryTr("add"))}</a>
        ) : canUpload ? (
          <Button type="button" size="md" variant="secondary" style={CONTROL} onClick={() => (uploadForm ? (setFormError(null), setForm({ row: null })) : setUploading(true))}>{addText}</Button>
        ) : canCreate && !hideAdd ? (
          <Button type="button" size="md" variant="secondary" style={CONTROL} onClick={() => { setFormError(null); setForm({ row: null }); }}>{addText}</Button>
        ) : null}
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "nowrap" }}>
        {pickable ? (
          <>
            <SelectAllBar keys={rows.map((row) => pkOf(table, row))} picked={picked} onPicked={(next) => setPicked(new Set([...next].map(String)))} label={galleryTr("select_all")} />
            {picked.size > 0 ? <Button type="button" size="sm" variant="danger" style={{ flex: "none", whiteSpace: "nowrap" }} onClick={() => setBulkAsking(true)}>{galleryTr("delete_selected", { count: picked.size })}</Button> : null}
          </>
        ) : null}
        <span style={{ flex: 1 }} />
        {config.infiniteScroll || config.simple ? null : config.paged ? (
          <PageBar paging={{ pageSize, offset, setOffset, setPageSize: (size) => { setPageSize(size); setOffset(0); } }} total={total} label={table.label} />
        ) : (
          <PageSizeSelect value={pageSize} onChange={(size) => { setPageSize(size); setOffset(0); }} />
        )}
      </div>
      <TermChips search={searchTerms} total={total} ready={!loading && !loadError} />
      {filterColumns.map((column) =>
        chips[column]?.length ? (
          <div key={column} role="group" aria-label={galleryTr("filters", { column })} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {chips[column].map((value) => (
              <Button key={value} type="button" size="sm" variant={filters[column] === value ? "primary" : "secondary"} aria-pressed={filters[column] === value} onClick={() => toggleFilter(column, value)}>{value}</Button>
            ))}
          </div>
        ) : null,
      )}
      {form && (editingRow ? canEdit : canCreate || canUpload) ? (
        <CrudRowForm
          key={editingRow ? pkOf(table, editingRow) : "new"}
          table={table}
          row={editingRow}
          labels={labels}
          busy={busy}
          error={formError}
          onSubmit={save}
          uploadFields={!editingRow && canUpload && uploadForm ? table.create_fields : undefined}
          onCancel={() => setForm(null)}
          stamp={editingRow ? stamps[pkOf(table, editingRow)] : undefined}
          onMediaReplaced={() => {
            if (editingRow) setStamps((previous) => ({ ...previous, [pkOf(table, editingRow)]: Date.now() }));
            reload();
          }}
        />
      ) : null}
      {uploading && !uploadForm && table.create_via ? <UploadDialog path={table.create_via} title={addLabel} accept={uploadAccept} onUploaded={reload} onClose={() => setUploading(false)} /> : null}
      {loadError ? <Alert>{loadError}</Alert> : null}
      {loading ? <p role="status" style={{ margin: 0 }}>{crudTr("loading")}</p> : null}
      {!loading && !loadError && rows.length === 0 ? <p className="muted" style={{ margin: 0 }}>{terms.length > 0 ? galleryTr("no_match", { terms: terms.join(", ") }) : pickLanguage(config.emptyText ?? galleryTr("empty"))}</p> : null}
      <div role="list" aria-label={galleryTr("cards", { table: table.label })} style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${columns}px, 1fr))`, gap: 12 }}>
        {rows.map((row) => (
          <div role="listitem" key={pkOf(table, row)} style={{ display: "flex", minWidth: 0 }}>
            <GalleryCard table={table} row={row} labels={labels} config={shownConfig} canEdit={Boolean(canEdit) && cardButtons} canDelete={canDelete && cardButtons} stamp={stamps[pkOf(table, row)]} owner={showOwner && String(row[config.ownerColumn!]) !== String(auth.status === "signed-in" ? auth.user.id : "") ? ownerOf(row, config.ownerColumn!, labels) : undefined} onEdit={() => { setFormError(null); setForm({ row }); }} onDelete={() => setDeleting(row)} actionContext={actionContext} onRename={canRename ? (value) => rename(row, value) : undefined} previewing={previewKey === pkOf(table, row)} onPreview={(open) => setPreviewKey(open ? pkOf(table, row) : null)} onStep={step} previewNav={previewNav} selected={picked.has(pkOf(table, row))} onSelect={pickable ? (on) => toggleSelected(pkOf(table, row), on) : undefined} renderThumb={renderThumb ? (column) => renderThumb(row, column) : undefined} renderMedia={renderMedia ? (column) => renderMedia(row, column) : undefined} onOpen={onOpen ? () => onOpen(row) : undefined} onField={onField ? (column) => onField(row, column) : undefined} onFieldSave={onFieldSave ? (column, text) => onFieldSave(row, column, text).then(() => reload()) : undefined} />
          </div>
        ))}
      </div>
      {more && config.infiniteScroll ? <div ref={sentinel} aria-hidden="true" style={{ height: 1 }} /> : null}
      {more && !config.infiniteScroll ? (
        <div style={{ textAlign: "center" }}>
          <Button type="button" variant="secondary" disabled={loading} onClick={() => setOffset(rows.length)}>{galleryTr("load_more")} ({galleryTr("shown", { shown: rows.length, total })})</Button>
        </div>
      ) : null}
      <ConfirmModal open={bulkAsking} message={galleryTr("confirm_delete_selected", { count: picked.size })} confirmLabel={crudTr("delete")} cancelLabel={crudTr("cancel")} onConfirm={() => void removeSelected()} onCancel={() => setBulkAsking(false)} />
      <ConfirmModal open={deleting !== null} message={crudTr("confirm_delete")} confirmLabel={crudTr("delete")} cancelLabel={crudTr("cancel")} onConfirm={remove} onCancel={() => setDeleting(null)} />
    </section>
  );
}


/** The text of one value of a row, with the label of a reference value. */
function textOf(column: ColumnInfo | undefined, row: Row, labels: Labels): string {
  if (!column) return "";
  const value = row[column.name];
  if (value === null || value === undefined) return "";
  if (column.type === "bool") return value === true || value === 1 || value === "true" ? humanize(column.name) : "";
  const label = column.ref ? labels[column.name]?.[String(value)] : undefined;
  if (typeof value === "object") return JSON.stringify(value);
  return label ?? String(value);
}

/** A status-like value as the same colored pill the table uses (the hue follows the text). */
function Badge({ value }: { value: string }) {
  const hue = hueOf(value);
  return <span className="sn-dt-badge" data-hue={hue} style={{ background: `color-mix(in srgb, var(--solid-${1 + (hue % 3)}) 28%, transparent)`, border: `1px solid color-mix(in srgb, var(--solid-${1 + (hue % 3)}) 55%, transparent)`, borderRadius: 999, padding: "0 8px", fontSize: 12 }}>{value}</span>;
}

/** The larger picture over the whole page: arrows at its sides, close at the top right, Edit / Delete / Download below. Keys: Escape, left, right. */
function Preview({ kind, src, name, title, owner, onClose, onStep, nav, onEdit, onDelete }: { kind: MediaKind; src: string; name: string; title: string; owner?: string; onClose: () => void; onStep?: (direction: -1 | 1) => void; nav?: PreviewNav; onEdit?: () => void; onDelete?: () => void }) {
  const dialog = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    dialog.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowLeft") onStep?.(-1);
      else if (event.key === "ArrowRight") onStep?.(1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, onStep]);
  const arrow = (side: "left" | "right"): CSSProperties => ({ position: "absolute", top: "50%", [side]: 8, transform: "translateY(-50%)", width: 48, height: 64, fontSize: 24 });
  return (
    <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-label={galleryTr("preview")} style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", flexDirection: "column", padding: 12, gap: 8, background: "var(--solid-0, #fff)", color: "var(--line, #16181d)", outline: "none" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <strong style={{ overflowWrap: "anywhere" }}>{title}</strong>
          <div className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{name}{owner ? ` · ${owner}` : ""}</div>
        </div>
        <Button type="button" variant="secondary" aria-label={crudTr("close")} title={crudTr("close")} onClick={onClose}>✕</Button>
      </div>
      <div style={{ position: "relative", flex: 1, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", borderRadius: 8, background: "color-mix(in srgb, var(--line, #000) 88%, #000)" }}>
        <MediaView kind={kind} src={src} name={name} big fill />
        {onStep && nav ? (
          <>
            <Button type="button" variant="secondary" style={arrow("left")} disabled={!nav.hasPrev} aria-label={galleryTr("previous")} onClick={() => onStep(-1)}>←</Button>
            <Button type="button" variant="secondary" style={arrow("right")} disabled={!nav.hasNext} aria-label={galleryTr("next")} onClick={() => onStep(1)}>→</Button>
          </>
        ) : null}
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        {nav ? <span role="status" className="muted" style={{ fontSize: 13 }}>{galleryTr("position", { index: nav.index, total: nav.total })}</span> : null}
        <span style={{ marginLeft: "auto", display: "inline-flex", gap: 6 }}>
          <a href={src} download={name} style={{ alignSelf: "center", fontSize: 14 }}>{galleryTr("download")}</a>
          {onEdit ? <Button type="button" variant="secondary" onClick={onEdit}>{galleryTr("edit")}</Button> : null}
          {onDelete ? <Button type="button" variant="danger" onClick={onDelete}>{galleryTr("delete")}</Button> : null}
        </span>
      </div>
    </div>
  );
}

/** Where the open picture is among the results: its place (1-based), how many there are, and whether a neighbour exists. */
export interface PreviewNav {
  index: number;
  total: number;
  hasPrev: boolean;
  hasNext: boolean;
}

export interface GalleryCardProps {
  table: TableInfo;
  row: Row;
  /** A shown field was double clicked. */
  onField?: (column: ColumnInfo) => void;
  /** A text field was changed in place: saves it (rejects with the reason). */
  onFieldSave?: (column: ColumnInfo, text: string) => Promise<void>;
  /** The card was double clicked: open the record. */
  onOpen?: () => void;
  /** The picture of the card, drawn by the app. */
  renderThumb?: (column: ColumnInfo) => ReactNode;
  /** A picture, audio or video field of the card, drawn by the app (its players) in place of a chip. */
  renderMedia?: (column: ColumnInfo) => ReactNode;
  labels: Labels;
  config: GalleryConfig;
  canEdit: boolean;
  canDelete: boolean;
  stamp?: number;
  /** The owner's name, shown as a chip at the top of the card (all-users mode). */
  owner?: string;
  onEdit: () => void;
  onDelete: () => void;
  /** Context handed to the custom actions. */
  actionContext?: GalleryActionContext;
  /** Saves a new title; rejects when it fails (the card shows the message). Present only when renaming is allowed. */
  onRename?: (value: string) => Promise<void>;
  /** Controlled preview: when given, the gallery decides which card shows the larger picture and what the arrow keys do. */
  previewing?: boolean;
  onPreview?: (open: boolean) => void;
  onStep?: (direction: -1 | 1) => void;
  previewNav?: PreviewNav;
  /** Selection for bulk actions: present when the gallery lets cards be ticked. */
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
}

const CLAMP_LINES = 2;

/** An amount kept in cents, as a number with two decimals in the language being shown. */
function money(cents: number): string {
  return (cents / 100).toLocaleString(intlLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** The title with its pencil: click either to edit in place; Enter saves, Escape cancels. */
function TitleEditor({ title, onRename, onError }: { title: string; onRename: (value: string) => Promise<void>; onError: (message: string | null) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function commit() {
    if (draft === null || saving) return;
    const next = draft.trim();
    if (next === "" || next === title) return setDraft(null);
    setSaving(true);
    onError(null);
    try {
      await onRename(next);
      setDraft(null);
    } catch (error) {
      onError(detailText(error));
    } finally {
      setSaving(false);
    }
  }
  function onKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      void commit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      setDraft(null);
      onError(null);
    }
  }
  if (draft === null) {
    return (
      <span style={{ display: "inline-flex", gap: 4, alignItems: "flex-start", minWidth: 0 }}>
        <h3 style={{ margin: 0, fontSize: 15, overflowWrap: "anywhere", cursor: "text" }} onClick={() => setDraft(title)}>{title}</h3>
        <button type="button" aria-label={`${galleryTr("rename")}: ${title}`} title={galleryTr("rename")} onClick={() => setDraft(title)} style={{ all: "unset", cursor: "pointer", fontSize: 13, lineHeight: "20px", padding: "0 4px" }}>✎</button>
      </span>
    );
  }
  return <input aria-label={galleryTr("rename_field")} value={draft} disabled={saving} autoFocus onChange={(event) => setDraft(event.target.value)} onKeyDown={onKeyDown} style={{ flex: 1, minWidth: 0, fontSize: 15 }} />;
}

/** One custom action as a button: busy while it runs, a confirmation first when asked for, its failure shown by the card. */
function ActionButton({ action, row, primary, context, title, onError }: { action: GalleryAction; row: Row; primary: boolean; context: GalleryActionContext; title: string; onError: (message: string | null) => void }) {
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  async function run() {
    setAsking(false);
    setBusy(true);
    onError(null);
    try {
      if (action.href) window.location.assign(action.href(row));
      else await action.run?.(row, context);
    } catch (error) {
      onError(detailText(error));
    } finally {
      setBusy(false);
    }
  }
  const variant = action.kind ?? (primary ? "primary" : "secondary");
  return (
    <>
      <Button type="button" size="sm" variant={variant} disabled={busy} aria-busy={busy} aria-label={`${pickLanguage(action.label)}: ${title}`} onClick={() => (action.confirm ? setAsking(true) : void run())}>
        {action.icon ? <span aria-hidden="true">{action.icon} </span> : null}{pickLanguage(action.label)}
      </Button>
      {action.confirm ? <ConfirmModal open={asking} message={action.confirm} confirmLabel={pickLanguage(action.label)} cancelLabel={crudTr("cancel")} onConfirm={() => void run()} onCancel={() => setAsking(false)} /> : null}
    </>
  );
}

/** One record as a card: thumbnail (opens the larger preview), title, badge, subtitle, clamped body, small facts and the Edit / Delete buttons. */
function GalleryCard({ table, row, labels, config, canEdit, canDelete, stamp, owner, onEdit, onDelete, actionContext, onRename, previewing, onPreview, onStep, previewNav, selected, onSelect, onField, onFieldSave, renderThumb, renderMedia, onOpen }: GalleryCardProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [localOpen, setLocalOpen] = useState(false);
  const open = previewing ?? localOpen;
  const setOpen = onPreview ?? setLocalOpen;
  const [broken, setBroken] = useState(false);
  const [inline, setInline] = useState<{ name: string; text: string; error: string } | null>(null);
  const column = (name?: string) => table.columns.find((candidate) => candidate.name === name);
  const title = textOf(column(config.title), row, labels) || pkOf(table, row);
  const titleField = column(config.title);
  const imageColumn = config.hideImage ? undefined : column(config.image);
  const kind = imageColumn?.media ? mediaKind(imageColumn.media) : "image";
  const src = imageColumn?.media ? mediaSrc(table, imageColumn, row, stamp) : null;
  const lean = config.density === "media";
  const subtitles = lean ? [] : (Array.isArray(config.subtitle) ? config.subtitle : config.subtitle ? [config.subtitle] : []).map((name) => textOf(column(name), row, labels)).filter((text) => text !== "" && text !== title);
  const badge = textOf(column(config.badge), row, labels);
  const rawBody = textOf(column(config.body), row, labels);
  const body = lean || rawBody.trim() === title.trim() ? "" : rawBody;
  const actions = (config.actions ?? []).filter((action) => !action.visible || action.visible(row));
  const metaColumns = (config.meta ?? []).filter((name) => name !== config.title && name !== config.image).map(column).filter((candidate): candidate is ColumnInfo => candidate !== undefined && row[candidate.name] != null && row[candidate.name] !== "" && !(config.quietFlags && candidate.type === "bool" && row[candidate.name] === true));
  const thumb: ReactNode =
    src && kind === "image" && !broken ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt="" loading="lazy" onError={() => setBroken(true)} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
    ) : (
      <span aria-hidden="true" style={{ fontSize: 28, opacity: 0.3 }}>{KIND_ICON[kind]}</span>
    );

  // A plain text field is changed in place; a picture, file or reference opens its dialog (onField).
  const startField = (meta: ColumnInfo) => {
    if (onFieldSave && !meta.media && !meta.ref && !meta.secret) setInline({ name: meta.name, text: textOfValue(row[meta.name]), error: "" });
    else onField?.(meta);
  };
  const commitField = async (meta: ColumnInfo) => {
    if (!inline || inline.name !== meta.name || !onFieldSave) return;
    const text = inline.text;
    if (text === (textOfValue(row[meta.name]))) return setInline(null);
    try {
      await onFieldSave(meta, text);
      setInline(null);
    } catch (failure) {
      setInline({ name: meta.name, text, error: failure instanceof Error ? failure.message : "Not saved" });
    }
  };

  return (
    <article aria-label={title} className="sn-gallery-card" onDoubleClick={onOpen ? (event) => { if (!(event.target as HTMLElement).closest("input, button, audio, video, a, [title]")) onOpen(); } : undefined} data-selected={selected ? "true" : undefined} style={{ position: "relative", flex: 1, display: "flex", flexDirection: "column", border: selected ? "2px solid var(--line)" : BORDER, borderRadius: 8, overflow: "hidden", background: SURFACE, minWidth: 0 }}>
      {onSelect && imageColumn && !renderThumb ? <input type="checkbox" className="sn-gallery-select" checked={Boolean(selected)} aria-label={`${galleryTr("select")} ${title}`} onChange={(event) => onSelect(event.target.checked)} style={{ position: "absolute", top: 8, left: 8, zIndex: 2, width: 18, height: 18 }} /> : null}
      {imageColumn && renderThumb ? (
          <div onClick={onField ? () => onField(imageColumn) : undefined} style={{ aspectRatio: "16 / 10", overflow: "hidden", cursor: onField ? "pointer" : undefined, background: "color-mix(in srgb, var(--line, #000) 6%, transparent)" }}>{renderThumb(imageColumn)}</div>
      ) : imageColumn ? (
        src ? (
          <button type="button" aria-label={galleryTr("open_preview", { name: fileName(String(row[imageColumn.name] ?? title)) })} onClick={() => setOpen(true)} style={{ all: "unset", cursor: "pointer", width: "100%", aspectRatio: "4 / 3", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--solid-2, transparent)", overflow: "hidden" }}>{thumb}</button>
        ) : (
          <div style={{ aspectRatio: "4 / 3", display: "flex", alignItems: "center", justifyContent: "center", background: "color-mix(in srgb, var(--line, #000) 6%, transparent)" }}>{thumb}</div>
        )
      ) : null}
      <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 6, flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "flex-start", justifyContent: badge ? "space-between" : "flex-start" }}>
          {onSelect && (!imageColumn || renderThumb) ? <input type="checkbox" className="sn-gallery-select" checked={Boolean(selected)} aria-label={`${galleryTr("select")} ${title}`} onChange={(event) => onSelect(event.target.checked)} style={{ width: 18, height: 18, flex: "none", marginTop: 2 }} /> : null}
          {config.hideTitle ? null : onRename ? <TitleEditor title={title} onRename={onRename} onError={setActionError} /> : inline && titleField && inline.name === titleField.name ? (
            <input
              aria-label={`${titleField.name} of ${title}`}
              value={inline.text}
              autoFocus
              onChange={(event) => setInline({ name: titleField.name, text: event.target.value, error: "" })}
              onKeyDown={(event) => { if (event.key === "Enter") void commitField(titleField); if (event.key === "Escape") setInline(null); }}
              onBlur={() => void commitField(titleField)}
              style={{ margin: 0, fontSize: 15, minWidth: 0, width: "100%", background: "transparent", color: "inherit", border: 0, borderBottom: "1px solid currentColor", font: "inherit" }}
            />
          ) : (
            <h3
              onClick={onField && titleField ? () => (onFieldSave && !titleField.media && !titleField.ref && titleField.type !== "json" ? setInline({ name: titleField.name, text: textOfValue(row[titleField.name]), error: "" }) : onField(titleField)) : undefined}
              style={{ margin: 0, fontSize: 15, overflowWrap: "anywhere", cursor: onField ? "pointer" : undefined }}
            >{title}</h3>
          )}
          {badge ? <Badge value={badge} /> : null}
        </div>
        {subtitles.length > 0 ? <small className="muted" style={{ overflowWrap: "anywhere" }}>{subtitles.join(" · ")}</small> : null}
        {body ? <p style={{ margin: 0, fontSize: 13, display: "-webkit-box", WebkitLineClamp: CLAMP_LINES, WebkitBoxOrient: "vertical", overflow: "hidden", overflowWrap: "anywhere" }} title={body}>{body}</p> : null}
        {metaColumns.length > 0 ? (
          <div style={renderMedia ? { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, max-content))", justifyContent: "start", gap: "4px 6px", fontSize: 12 } : { display: "flex", flexWrap: "wrap", gap: "4px 6px", fontSize: 12 }}>
            {metaColumns.map((meta) => renderMedia && meta.media ? (
              <div key={meta.name} onClick={onField ? () => onField(meta) : undefined} style={{ gridColumn: "1 / -1", cursor: onField ? "pointer" : undefined }}>{renderMedia(meta)}</div>
            ) : (
              <span key={meta.name} title={onField ? "Click to change" : undefined} onClick={onField ? () => startField(meta) : undefined} style={{ display: "inline-flex", gap: 4, border: BORDER, maxWidth: "100%", overflowWrap: "anywhere", cursor: onField ? "pointer" : undefined, ...(renderMedia ? { flexDirection: "column", alignItems: "flex-start", borderRadius: 8, padding: "4px 8px", minWidth: 0 } : { borderRadius: 999, padding: "0 8px", minWidth: 120, boxSizing: "border-box" }) }}>
                <span className="muted" style={{ whiteSpace: "nowrap" }}>{config.quietFlags && meta.type === "bool" ? `${galleryTr("not")} ${humanize(meta.name).toLowerCase()}` : humanize(meta.name).replace(/ cents$/i, "")}</span>
                {inline?.name === meta.name && meta.type === "json" ? (
                  <textarea
                    aria-label={`${meta.name} of ${title}`}
                    value={inline.text}
                    autoFocus
                    rows={4}
                    spellCheck={false}
                    onChange={(event) => setInline({ ...inline, text: event.target.value, error: "" })}
                    onKeyDown={(event) => { if (event.key === "Escape") setInline(null); }}
                    onBlur={() => void commitField(meta)}
                    style={{ width: "100%", minWidth: 200, fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12, background: "transparent", color: "inherit", border: BORDER, borderRadius: 4, padding: 4 }}
                  />
                ) : inline?.name === meta.name ? (
                  <input
                    aria-label={`${meta.name} of ${title}`}
                    value={inline.text}
                    autoFocus
                    onChange={(event) => setInline({ ...inline, text: event.target.value, error: "" })}
                    onKeyDown={(event) => { if (event.key === "Enter") void commitField(meta); if (event.key === "Escape") setInline(null); }}
                    onBlur={() => void commitField(meta)}
                    style={{ minWidth: 120, background: "transparent", color: "inherit", border: 0, borderBottom: "1px solid currentColor", font: "inherit" }}
                  />
                ) : config.quietFlags && meta.type === "bool" ? null : meta.name.endsWith("_cents") && typeof row[meta.name] === "number" ? <span>{money(row[meta.name] as number)}</span> : <span style={meta.ref && onField ? { textDecoration: "underline dotted" } : undefined}><CellView column={meta} value={row[meta.name]} labels={labels[meta.name]} table={table} row={row} stamp={stamp} /></span>}
                {inline?.name === meta.name && inline.error ? <span role="alert" style={{ color: "#ffb4b4" }}>{inline.error}</span> : null}
              </span>
            ))}
          </div>
        ) : null}
        {actionError ? <p role="alert" style={{ margin: 0, fontSize: 12 }}>{actionError}</p> : null}
        {owner || actions.length > 0 || canEdit || canDelete ? (
          <div className="sn-gallery-actions" style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginTop: "auto", paddingTop: 4 }}>
            {owner ? <span data-testid="owner-chip" title={galleryTr("owner", { owner })} style={{ display: "inline-block", maxWidth: "50%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", border: BORDER, borderRadius: 999, padding: "0 8px", fontSize: 12, marginRight: "auto", background: "var(--solid-2, transparent)" }}>{owner}</span> : null}
            {actionContext ? actions.map((action, index) => <ActionButton key={action.key} action={action} row={row} primary={index === 0} context={actionContext} title={title} onError={setActionError} />) : null}
            {canEdit ? <Button size="sm" variant="secondary" style={NOWRAP_STYLE} aria-label={`${galleryTr("edit")} ${title}`} title={galleryTr("edit")} onClick={onEdit}>{galleryTr("edit")}</Button> : null}
            {canDelete ? <Button size="sm" variant="danger" style={NOWRAP_STYLE} aria-label={`${galleryTr("delete")} ${title}`} title={galleryTr("delete")} onClick={onDelete}>{galleryTr("delete")}</Button> : null}
          </div>
        ) : null}
      </div>
      {open && src ? <Preview kind={kind} src={src} title={title} owner={owner} name={fileName(String(row[imageColumn!.name] ?? title))} onClose={() => setOpen(false)} onStep={onStep} nav={previewNav} onEdit={canEdit ? () => { setOpen(false); onEdit(); } : undefined} onDelete={canDelete ? () => { setOpen(false); onDelete(); } : undefined} /> : null}
    </article>
  );
}

interface GridViewProps<T> {
  items: readonly T[];
  itemKey: (item: T) => Key;
  renderItem: (item: T) => ReactNode;
  /** The name of the grid for people who cannot see it. */
  label: string;
  /** The narrowest a column gets, in pixels: as many columns as fit are made, all of the same width. */
  minColumnWidth?: number;
  gap?: number;
  /** Shown instead of the grid when there is nothing in it. */
  empty?: ReactNode;
}

/** Items in a responsive grid of equal columns (a gallery): the columns follow the width of the window, and every item fills its cell. */
export function GridView<T>({ items, itemKey, renderItem, label, minColumnWidth = 180, gap = 10, empty = null }: GridViewProps<T>) {
  if (items.length === 0) return <>{empty}</>;
  return (
    <ul
      aria-label={label}
      style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${minColumnWidth}px, 1fr))`, gap }}
    >
      {items.map((item) => (
        <li key={itemKey(item)} style={{ minWidth: 0 }}>
          {renderItem(item)}
        </li>
      ))}
    </ul>
  );
}
