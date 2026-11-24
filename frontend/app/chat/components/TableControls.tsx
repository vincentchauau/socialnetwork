"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";

import { ColumnsMenu } from "@sn/compounds/TableFooter";
import { PAGE_SIZES } from "@sn/compounds/InputBox";
import { CONTROL, PageBar, SelectAllBar as SharedSelectAll } from "@sn/compounds/TableFooter";
export { CONTROL, PageBar };

/** The chat's "Select all" (its words come from the chat's translations). */
export function SelectAllBar(props: Omit<Parameters<typeof SharedSelectAll>[0], "label">) {
  return <SharedSelectAll label={tr("rm_chon_tat_ca")} {...props} />;
}
import type { Column, Key, Sort } from "@sn/compounds/DataTable";
import { tr } from "../i18n";


const COLUMNS_KEY = "sn_cols2_chat_";

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** The rows in the order of the column pressed (by its `sortValue`), or as they came: the order is made before the page is cut. */
export function sortRows<T>(rows: T[], columns: Column<T>[], sort: Sort): T[] {
  const value = sort ? columns.find((column) => column.key === sort.key)?.sortValue : undefined;
  if (!sort || !value) return rows;
  const factor = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    return factor * (typeof x === "number" && typeof y === "number" ? x - y : collator.compare(String(x), String(y)));
  });
}

/** Which columns of a table are shown, remembered in this browser under `name`; a menu (the Columns button) changes them. */
export function useColumns(name: string, columns: { key: string; label: string }[], hiddenAtFirst: string[] = []): { shown: ReadonlySet<string>; menu: ReactNode } {
  const storage = COLUMNS_KEY + name;
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set(hiddenAtFirst));
  useEffect(() => {
    try {
      const kept = window.localStorage.getItem(storage);
      if (kept === null) return; // never chosen: the columns that start hidden stay so
      const stored: unknown = JSON.parse(kept);
      if (Array.isArray(stored)) setHidden(new Set(stored.filter((key): key is string => typeof key === "string")));
    } catch {
      // not remembered: every column shows
    }
  }, [storage]);
  const keys = columns.map((column) => column.key).join("|");
  const shown = useMemo(() => new Set(keys.split("|").filter((key) => !hidden.has(key))), [keys, hidden]);
  const toggle = (key: string, on: boolean) => {
    const next = new Set(hidden);
    if (on) next.delete(key);
    else next.add(key);
    setHidden(next);
    try {
      window.localStorage.setItem(storage, JSON.stringify([...next]));
    } catch {
      // not remembered: fine
    }
  };
  return { shown, menu: <ColumnsMenu label={tr("rm_cot")} columns={columns} shown={shown} onToggle={toggle} buttonStyle={CONTROL} /> };
}

/** The page of a table whose rows are all in hand: how many rows a page has, and where it starts. */
export function usePaging(total: number) {
  const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    if (offset > 0 && offset >= total) setOffset(Math.max(0, Math.floor((total - 1) / pageSize) * pageSize));
  }, [offset, total, pageSize]);
  return {
    pageSize,
    offset,
    setOffset,
    setPageSize: (size: number) => {
      setPageSize(size);
      setOffset(0);
    },
    page: <T,>(rows: T[]): T[] => rows.slice(offset, offset + pageSize),
  };
}

