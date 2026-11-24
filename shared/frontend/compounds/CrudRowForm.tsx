"use client";

import { type CSSProperties, type FormEvent, useEffect, useState, type ChangeEvent, type KeyboardEvent as ReactKeyboardEvent, useId, useRef } from "react";
import Alert from "../elements/Alert";
import Button from "../elements/Button";
import Card from "../elements/Card";
import CheckBox from "../elements/CheckBox";
import { BG, FG, BORDER } from "../lib/theme";
import { useSession } from "../lib/useSession";
import { formatDateTime } from "./CellView";
import FileDropZone from "./FileTools";
import LabelTextBox, { type LabelTextBoxProps } from "./LabelTextBox";
import { MediaView } from "./FileTools";
import { MediaField } from "./FileTools";
import { type ColumnInfo, type Draft, type Labels, type Row, type TableInfo, crudTr, draftOf, fileName, humanize, isLocked, mediaKind, mediaSrc } from "./crudModel";
import { apiFetch } from "../api";

export interface CrudRowFormProps {
  table: TableInfo;
  /** The row being changed; null: a new row. */
  row: Row | null;
  /** The text of the values of reference columns, when known. */
  labels?: Labels;
  busy: boolean;
  error: string | null;
  onSubmit: (draft: Draft, file?: File | null) => void;
  onCancel: () => void;
  /** Changes after a media replacement (busts the browser cache of the pictures). */
  stamp?: number;
  /** A media column's file was replaced: the table should reload. */
  onMediaReplaced?: () => void;
  /** The module base (e.g. "/api/market/records"): with it, text fields offer suggestions while typed. */
  api?: string;
  /** A new row is made by uploading a file: the form shows only `uploadFields`, and a drop zone where the file column is. */
  uploadFields?: string[];
}

const LOCKED_STYLE: CSSProperties = {
  background: "color-mix(in srgb, var(--line) 9%, transparent)",
  opacity: 0.8,
  cursor: "not-allowed",
  outline: "none",
};
const LABEL_SIZE = 14;
const FULL_ROW: CSSProperties = { gridColumn: "1 / -1" };
const GRID: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 };

/** Puts the id of the signed-in person in the owner column (a reference to users) of a new row, for a person who is not an admin. */
function OwnerPrefill({ onUser }: { onUser: (id: number) => void }) {
  const auth = useSession();
  const user = auth.status === "signed-in" ? auth.user : null;
  const id = user && user.group !== "admin" && typeof user.id === "number" ? user.id : null;
  useEffect(() => {
    if (id !== null) onUser(id);
  }, [id, onUser]);
  return null;
}

const isOwnerColumn = (column: ColumnInfo) => column.ref?.table === "users";

/** The form to add or change one row, in a dialog over the table. Escape or a click outside closes it. */
export default function CrudRowForm({ table, row, labels, busy, error, onSubmit, onCancel, stamp, onMediaReplaced, api, uploadFields }: CrudRowFormProps) {
  const editing = row !== null;
  const uploading = !editing && uploadFields !== undefined;
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<Draft>(() => draftOf(table, row));
  const [picked, setPicked] = useState<Record<string, { id: string; label: string }>>({});
  const set = (name: string, value: string | boolean) => setDraft((previous) => ({ ...previous, [name]: value }));
  const title = crudTr(editing ? "edit_title" : "create_title");
  const ownerColumns = table.columns.filter(isOwnerColumn).map((column) => column.name);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const fillOwner = (id: number) =>
    setDraft((previous) => {
      const next = { ...previous };
      for (const name of ownerColumns) if (next[name] === "") next[name] = String(id);
      return next;
    });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (uploading) onSubmit(draft, file);
    else onSubmit(draft);
  };

  const lockedCaption = (
    <>
      <span aria-hidden="true">🔒</span>
      <small className="muted">{crudTr("read_only")}</small>
    </>
  );

  function renderField(column: ColumnInfo) {
    if (uploading && column.media?.replace) {
      return (
        <div key={column.name} style={FULL_ROW}>
          <div title={column.name} style={{ fontSize: LABEL_SIZE, fontWeight: 600, marginBottom: 4 }}>{humanize(column.name)}</div>
          <FileDropZone accept={column.media.accept} busy={busy} inputLabel={humanize(column.name)} testId="create-drop" prompt={file ? file.name : crudTr("upload_prompt")} onFiles={(files) => setFile(files[0] ?? null)} />
        </div>
      );
    }
    const locked = isLocked(table, column, editing);
    const label = humanize(column.name);
    if (column.type === "bool") {
      return <CheckBox key={column.name} label={label} checked={Boolean(draft[column.name])} disabled={locked || busy} onChange={(checked) => set(column.name, checked)} />;
    }
    if (editing && column.media?.replace && row) {
      return (
        <div key={column.name} style={FULL_ROW}>
          <div title={column.name} style={{ fontSize: LABEL_SIZE, fontWeight: 600, marginBottom: 4 }}>{label}</div>
          <MediaField table={table} column={column} row={row} stamp={stamp} onReplaced={() => onMediaReplaced?.()} />
        </div>
      );
    }
    const masked = column.secret || column.type === "bytes";
    const key = String(draft[column.name] ?? "");
    const pickedLabel = picked[column.name]?.id === key ? picked[column.name].label : undefined;
    const known = column.ref ? (labels?.[column.name]?.[key] ?? pickedLabel) : undefined;
    const original = row && column.ref ? String(row[column.name] ?? "") : null;
    const relinked = original !== null && key !== original;
    const isDate = column.type === "datetime";
    const wide = column.type === "text" || column.type === "json";
    let value = key;
    if (masked && locked) value = "***";
    else if (isDate && locked && row?.[column.name] != null) value = formatDateTime(row[column.name]);
    const needsOwner = !editing && isOwnerColumn(column);
    const src = row && column.media?.preview ? mediaSrc(table, column, row, stamp) : null;
    const suggests = Boolean(api) && !locked && !column.secret && (column.type === "string" || Boolean(column.ref));
    const onPick = (id: string, text?: string) => {
      set(column.name, id);
      if (column.ref && text) setPicked((previous) => ({ ...previous, [column.name]: { id, label: text } }));
    };
    const fieldProps = {
      label,
      title: column.name,
      labelSize: LABEL_SIZE,
      adornment: locked ? lockedCaption : needsOwner ? <small className="muted">* {crudTr("ref_required")}</small> : undefined,
      fieldStyle: locked ? LOCKED_STYLE : undefined,
      name: column.name,
      type: column.type === "text" || column.type === "json" ? ("textarea" as const) : ("text" as const),
      value,
      required: needsOwner,
      disabled: locked || busy,
      placeholder: column.secret && editing ? crudTr("secret_keep") : undefined,
      inputType: column.secret ? "password" : isDate && !locked ? "datetime-local" : undefined,
    };
    return (
      <div key={column.name} style={wide ? FULL_ROW : undefined}>
        {suggests && api ? (
          <SuggestField {...fieldProps} api={api} table={table.name} column={column.name} reference={Boolean(column.ref)} onText={(text) => set(column.name, text)} onPick={onPick} />
        ) : (
          <LabelTextBox {...fieldProps} onChange={(event) => set(column.name, event.target.value)} />
        )}
        {src && column.media ? (
          <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 8 }}>
            <MediaView kind={mediaKind(column.media)} src={src} name={fileName(key)} />
          </div>
        ) : null}
        {known ? <small className="muted" data-testid={`ref-label-${column.name}`}>{known}</small> : null}
        {relinked ? <div role="note" data-testid={`ref-warning-${column.name}`} style={{ fontSize: 13, color: "var(--danger, #b45309)" }}>⚠ {crudTr("ref_changed")}</div> : null}
      </div>
    );
  }

  const uploadColumns = uploading ? [...table.columns.filter((column) => column.media?.replace), ...table.columns.filter((column) => uploadFields!.includes(column.name))] : [];
  const writable = uploading ? uploadColumns : table.columns.filter((column) => !isLocked(table, column, editing) || Boolean(editing && column.media?.replace));
  const system = editing ? table.columns.filter((column) => !writable.includes(column)) : [];

  return (
    <div
      data-testid="row-form-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
      style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 12, background: "color-mix(in srgb, var(--line, #000) 45%, transparent)" }}
    >
      <form onSubmit={submit} role="dialog" aria-modal="true" aria-label={title} noValidate style={{ width: "100%", maxWidth: 760, maxHeight: "90vh", overflow: "auto" }}>
        <Card stack style={{ background: BG, color: FG }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          {!editing && !uploading && ownerColumns.length > 0 ? <OwnerPrefill onUser={fillOwner} /> : null}
          <div style={GRID}>{writable.map(renderField)}</div>
          {system.length > 0 ? (
            <details open data-testid="system-info">
              <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: LABEL_SIZE, marginBottom: 8 }}>{crudTr("system_info")}</summary>
              <div style={GRID}>{system.map(renderField)}</div>
            </details>
          ) : null}
          {error ? <Alert>{error}</Alert> : null}
          <div style={{ display: "flex", gap: 8 }}>
            <Button type="submit" disabled={busy}>{crudTr("save")}</Button>
            <Button type="button" variant="secondary" onClick={onCancel}>{crudTr("cancel")}</Button>
          </div>
        </Card>
      </form>
    </div>
  );
}

export interface Suggestion {
  value: string;
  label: string;
}

export interface SuggestFieldProps extends Omit<LabelTextBoxProps, "onChange" | "id"> {
  /** Admin or data base of the module, e.g. "/api/market/records". */
  api: string;
  table: string;
  /** The column asked about. */
  column: string;
  /** Called with the typed text. */
  onText: (text: string) => void;
  /** Called when a suggestion is chosen (a reference option carries its label). */
  onPick: (value: string, label?: string) => void;
  /** A reference column: the text typed is a name to look up, so a stored id is not searched on focus. */
  reference?: boolean;
}

const DEBOUNCE_MS = 200;
const LIST_STYLE: CSSProperties = {
  position: "absolute", left: 0, right: 0, top: "100%", zIndex: 5, margin: 0, padding: 4, listStyle: "none",
  maxHeight: 220, overflowY: "auto", background: BG, color: FG, border: `1px solid ${BORDER}`, borderRadius: 6,
};

/** Reads a suggest answer into a list: plain values, or reference options (label shown, id kept). */
function toSuggestions(data: unknown): Suggestion[] {
  if (!data || typeof data !== "object") return [];
  const { values, options } = data as { values?: unknown; options?: unknown };
  if (Array.isArray(options) && options.length > 0) {
    return options
      .filter((o): o is { value: string | number; label: string } => !!o && typeof o === "object" && "value" in o && typeof (o as { label?: unknown }).label === "string")
      .map((o) => ({ value: String(o.value), label: o.label }));
  }
  return Array.isArray(values) ? values.filter((v): v is string => typeof v === "string").map((v) => ({ value: v, label: v })) : [];
}

/** A text field that offers values of its column while it is typed in. Free text is always allowed. */
function SuggestField({ api, table, column, onText, onPick, reference = false, value, disabled, ...field }: SuggestFieldProps) {
  const listId = `${useId()}-list`;
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const text = String(value ?? "");
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!query.trim() || disabled) {
      setItems([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const url = `${api}/${encodeURIComponent(table)}/suggest?column=${encodeURIComponent(column)}&q=${encodeURIComponent(query)}`;
      apiFetch<unknown>(url, { signal: controller.signal })
        .then((data) => {
          if (controller.signal.aborted) return;
          setItems(toSuggestions(data));
          setActive(-1);
        })
        .catch(() => {
          if (!controller.signal.aborted) setItems([]);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, table, column, query, disabled]);

  useEffect(() => () => { if (blurTimer.current) clearTimeout(blurTimer.current); }, []);

  const shown = open ? items.filter((item) => item.value !== text) : [];
  const expanded = shown.length > 0;
  const optionId = (index: number) => `${listId}-${index}`;

  const choose = (item: Suggestion) => {
    onPick(item.value, item.label);
    setQuery("");
    setItems([]);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (!expanded) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => (index + step + shown.length) % shown.length);
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      choose(shown[active]);
    } else if (event.key === "Escape") {
      event.nativeEvent.stopImmediatePropagation();
      setOpen(false);
    }
  };

  return (
    <LabelTextBox
      {...field}
      value={value}
      disabled={disabled}
      onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        onText(event.target.value);
        setQuery(event.target.value);
        setOpen(true);
      }}
      inputProps={{
        role: "combobox",
        autoComplete: "off",
        "aria-autocomplete": "list",
        "aria-expanded": expanded,
        "aria-controls": listId,
        "aria-activedescendant": expanded && active >= 0 ? optionId(active) : undefined,
        onKeyDown,
        onFocus: () => {
          if (blurTimer.current) clearTimeout(blurTimer.current);
          if (text && !reference) setQuery(text);
          setOpen(true);
        },
        onBlur: () => {
          blurTimer.current = setTimeout(() => setOpen(false), 120);
        },
      }}
      afterInput={
        <ul id={listId} role="listbox" aria-label={crudTr("suggestions")} hidden={!expanded} style={expanded ? LIST_STYLE : undefined}>
          {shown.map((item, index) => (
            <li
              key={item.value}
              id={optionId(index)}
              role="option"
              aria-selected={index === active}
              onMouseDown={(event) => {
                event.preventDefault();
                choose(item);
              }}
              onMouseEnter={() => setActive(index)}
              style={{ padding: "4px 8px", cursor: "pointer", borderRadius: 4, background: index === active ? "color-mix(in srgb, var(--line, #888) 20%, transparent)" : undefined }}
            >
              {item.label}
            </li>
          ))}
        </ul>
      }
    />
  );
}
