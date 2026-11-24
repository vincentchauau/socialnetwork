"use client";

import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";

import Button from "../elements/Button";
import CheckBox from "../elements/CheckBox";
import { PAGE_SIZES, PageSizeSelect } from "./InputBox";
import { crudTr } from "./crudModel";
type Key = string | number;

/** One size for every control of the bar (the search box and the buttons), the same as the Table pane's, so they line up. */
export const CONTROL = { height: 36, boxSizing: "border-box", fontSize: 14, lineHeight: "20px", padding: "0 14px", whiteSpace: "nowrap" } as const;

export interface PageBarProps {
  paging: { pageSize: number; offset: number; setOffset: (offset: number) => void; setPageSize: (size: number) => void };
  total: number;
  /** What the table is of: names the footer for people who cannot see it. */
  label: string;
}

/** What the Table pane has under its bar and the tables of the chat have too: the rows a page has, previous and next. */
export function PageBar({ paging, total, label }: PageBarProps) {
  const { pageSize, offset, setOffset, setPageSize } = paging;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + pageSize, total);
  return (
    <>
      <PageSizeSelect value={pageSize} onChange={setPageSize} />
      {total > pageSize ? (
        <span style={{ marginLeft: "auto" }}>
        <Pager
          label={label}
          from={from}
          to={to}
          total={total}
          rangeText={crudTr("page", { from, to, total })}
          prevLabel={crudTr("prev")}
          nextLabel={crudTr("next")}
          onPrev={() => setOffset(Math.max(0, offset - pageSize))}
          onNext={() => setOffset(offset + pageSize)}
        />
        </span>
      ) : null}
    </>
  );
}

/** "Select all" over the rows of the page that may be picked, as a line over the table (the Table pane has no box in the head). */
export function SelectAllBar({ keys, picked, onPicked, label = "Select all" }: { keys: Key[]; picked: ReadonlySet<Key>; onPicked: (picked: ReadonlySet<Key>) => void; label?: string }) {
  return (
    <label style={{ display: "inline-flex", gap: 6, alignItems: "center", height: 36, fontSize: 14, fontWeight: 600, alignSelf: "center" }}>
      <CheckBox disabled={keys.length === 0} checked={keys.length > 0 && keys.every((key) => picked.has(key))} onChange={(checked) => onPicked(checked ? new Set(keys) : new Set())} />
      {label}
    </label>
  );
}

export interface PagerProps {
  from: number;
  to: number;
  total: number;
  disabled?: boolean;
  onPrev: () => void;
  onNext: () => void;
  /** The text of the range, e.g. "1-20 of 134". */
  rangeText: string;
  prevLabel: string;
  nextLabel: string;
  label: string;
}

/** The footer of a paged table: previous, the range, next. */
export function Pager({ from, to, total, disabled = false, onPrev, onNext, rangeText, prevLabel, nextLabel, label }: PagerProps) {
  return (
    <nav aria-label={label} style={{ display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", height: 36, fontSize: 14 }}>
      <span role="status" style={{ whiteSpace: "nowrap" }}>{rangeText}</span>
      <Button size="sm" variant="secondary" style={{ flex: "none", height: 36 }} disabled={disabled || from <= 1} onClick={onPrev}>{prevLabel}</Button>
      <Button size="sm" variant="secondary" style={{ flex: "none", height: 36 }} disabled={disabled || to >= total} onClick={onNext}>{nextLabel}</Button>
    </nav>
  );
}

export interface ColumnsMenuProps {
  label: string;
  columns: { key: string; label: string }[];
  shown: ReadonlySet<string>;
  onToggle: (key: string, on: boolean) => void;
  /** While true the list stays closed (another dialog is open). */
  suspended?: boolean;
  /** Style of the button, so it can match its neighbours in a toolbar. */
  buttonStyle?: CSSProperties;
}

/** A button that opens the list of columns with a box each, to show or hide any of them. */
export function ColumnsMenu({ label, columns, shown, onToggle, suspended = false, buttonStyle }: ColumnsMenuProps) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onDown = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);
  const visible = open && !suspended;
  return (
    <div ref={box} style={{ position: "relative", display: "flex", alignItems: "center" }}>
      <Button type="button" size="md" variant="secondary" style={buttonStyle} aria-expanded={visible} aria-haspopup="true" onClick={() => setOpen(!open)}>{label}</Button>
      {visible ? (
        <div role="group" aria-label={label} style={{ position: "absolute", right: 0, top: "100%", zIndex: 5, minWidth: 180, maxHeight: 280, overflow: "auto", padding: 8, marginTop: 4, display: "flex", flexDirection: "column", gap: 4, background: "var(--solid-0)", border: "1px solid color-mix(in srgb, var(--line) 40%, transparent)", borderRadius: 6 }}>
          {columns.map((column) => (
            <label key={column.key} style={{ display: "flex", gap: 6, alignItems: "center", whiteSpace: "nowrap" }}>
              <input type="checkbox" checked={shown.has(column.key)} onChange={(event) => onToggle(column.key, event.target.checked)} />
              {column.label}
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
