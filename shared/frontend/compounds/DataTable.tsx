"use client";

import { type MouseEvent, type ReactNode, useMemo, useState } from "react";

import CheckBox from "../elements/CheckBox";
import { crudTr as tr } from "./crudModel";
import Button from "../elements/Button";

export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  /** A narrow column keeps its size (a number, a date); the others share what is left. */
  narrow?: boolean;
  /** A class for the cells of the column. */
  className?: string;
  /** What the rows are ordered by when the head of the column is pressed (left out: the column is not sortable). */
  sortValue?: (row: T) => string | number;
}

export type Key = string | number;

interface Props<T> {
  /** What the table is of: names it for people who cannot see it. */
  label: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => Key;
  /** Which rows may be picked (the others have no box): "only if owner", "only if sender". */
  pickable?: (row: T) => boolean;
  picked: ReadonlySet<Key>;
  onPicked: (picked: ReadonlySet<Key>) => void;
  /** The actions of one row, in the same order on every table: open, edit, delete… */
  actions?: (row: T) => ReactNode;
  /** What names a row for people who cannot see it. */
  rowLabel?: (row: T) => string;
  /** The row the person is in now. */
  current?: (row: T) => boolean;
  /** A line over a row that says something before it (a day, "unread messages"): nothing for most rows. */
  before?: (row: T) => ReactNode;
  /** The table has no head (a conversation reads from the top). */
  headless?: boolean;
  empty: string;
  /** The order is kept by the owner (the rows come from a server already in it): the heads only say which column and which way. */
  sort?: Sort;
  onSort?: (next: Sort) => void;
  /** The box that picks every row in the head (default); leave it out when a bar over the table does that, as the Table pane does. */
  headerSelect?: boolean;
  /** A file list: a click on a row picks it (Ctrl, Shift or Cmd keeps the others), and a double click opens it. */
  onOpen?: (row: T) => void;
}

/**
 * The one table of the chat, for the rooms, the members and the messages: a box to pick (only where the row may be acted on), the columns
 * that matter, and the actions of the row at its end. The box of the head picks every row that can be picked.
 */
export type Sort = { key: string; direction: "asc" | "desc" } | null;

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export default function DataTable<T>({ label, columns, rows, rowKey, pickable = () => true, picked, onPicked, actions, rowLabel, current, before, headless = false, empty, sort: ownerSort, onSort, headerSelect = true, onOpen }: Props<T>) {
  const [own, setSort] = useState<Sort>(null);
  const sort = onSort ? (ownerSort ?? null) : own;
  const shown = useMemo(() => {
    if (onSort) return rows;
    const column = sort ? columns.find((candidate) => candidate.key === sort.key) : undefined;
    if (!sort || !column?.sortValue) return rows;
    const value = column.sortValue;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = value(a);
      const y = value(b);
      return factor * (typeof x === "number" && typeof y === "number" ? x - y : collator.compare(String(x), String(y)));
    });
  }, [rows, columns, sort, onSort]);
  // Pressing a head: ascending, then descending, then the order the rows came in.
  const next = (current: Sort, key: string): Sort => (current?.key !== key ? { key, direction: "asc" } : current.direction === "asc" ? { key, direction: "desc" } : null);
  const press = (key: string) => (onSort ? onSort(next(sort, key)) : setSort((current) => next(current, key)));
  const canPick = rows.filter(pickable);
  const allPicked = canPick.length > 0 && canPick.every((row) => picked.has(rowKey(row)));
  const toggle = (key: Key) => {
    const next = new Set(picked);
    if (!next.delete(key)) next.add(key);
    onPicked(next);
  };

  /** A click on the row itself (not on a button, a link or a box in it) picks it, as in a file list. */
  const clicked = (row: T, event: MouseEvent<HTMLTableRowElement>) => {
    if (!onOpen || !pickable(row) || (event.target as HTMLElement).closest("button, a, input, label, select, textarea")) return;
    const key = rowKey(row);
    if (event.ctrlKey || event.metaKey || event.shiftKey) return toggle(key);
    onPicked(picked.size === 1 && picked.has(key) ? new Set() : new Set([key]));
  };

  if (rows.length === 0) {
    return (
      <p className="cw-empty" role="status">
        {empty}
      </p>
    );
  }
  return (
    <div className="cw-table-wrap">
      <table className="cw-table" aria-label={label}>
        <thead hidden={headless}>
          <tr>
            <th className="cw-col-pick">
              {headerSelect && (
                <CheckBox
                  checked={allPicked}
                  indeterminate={!allPicked && canPick.some((row) => picked.has(rowKey(row)))}
                  disabled={canPick.length === 0}
                  aria-label={tr("select_all_rows")}
                  onChange={(checked) => onPicked(checked ? new Set(canPick.map(rowKey)) : new Set())}
                />
              )}
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={[column.narrow ? "cw-col-narrow" : "", column.className ?? ""].join(" ").trim() || undefined}
                aria-sort={sort?.key === column.key ? (sort.direction === "asc" ? "ascending" : "descending") : column.sortValue ? "none" : undefined}
              >
                {column.sortValue ? (
                  <Button type="button" variant="ghost" size="sm" className="cw-sort" onClick={() => press(column.key)}>
                    {column.label}
                    <span aria-hidden="true" className="cw-arrow" data-active={sort?.key === column.key ? "true" : undefined}>{sort?.key === column.key ? (sort.direction === "asc" ? " ▲" : " ▼") : " ↕"}</span>
                  </Button>
                ) : (
                  column.label
                )}
              </th>
            ))}
            {actions && <th scope="col" className="cw-col-actions">{tr("actions_column")}</th>}
          </tr>
        </thead>
        <tbody>
          {shown.map((row) => {
            const key = rowKey(row);
            const lead = sort ? null : before?.(row); // the lines between days only mean something in the order of the day
            return [
              lead ? (
                <tr key={`${key}-before`} className="cw-sep">
                  <td colSpan={columns.length + 1 + (actions ? 1 : 0)}>{lead}</td>
                </tr>
              ) : null,
              <tr
                key={key}
                aria-current={current?.(row) ? "true" : undefined}
                aria-selected={onOpen ? picked.has(key) : undefined}
                data-picked={picked.has(key) ? "true" : undefined}
                onClick={onOpen ? (event) => clicked(row, event) : undefined}
                onDoubleClick={onOpen ? () => onOpen(row) : undefined}
              >
                <td className="cw-col-pick">
                  {pickable(row) && <CheckBox checked={picked.has(key)} aria-label={`${tr("select_row")} ${rowLabel?.(row) ?? String(key)}`} onChange={() => toggle(key)} />}
                </td>
                {columns.map((column) => (
                  <td key={column.key} className={[column.narrow ? "cw-col-narrow" : "", column.className ?? ""].join(" ").trim() || undefined}>
                    {column.render(row)}
                  </td>
                ))}
                {actions && <td className="cw-col-actions">{actions(row)}</td>}
              </tr>,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}
