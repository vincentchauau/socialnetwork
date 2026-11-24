"use client";

import { type ReactNode, createContext, useCallback, useContext, useMemo, useState } from "react";

import { useDatabaseSelection } from "../../selection";

/** The cell that asked for a record: the table, the row and the reference column it sits in. */
export interface PickOrigin {
  database: string;
  table: string;
  key: string;
  column: string;
}

/** The referenced table the Table tab shows to choose a record in: the app that owns it, its key column and its label column. */
export interface PickTarget {
  database: string;
  table: string;
  keyColumn: string;
  labelColumn: string;
}

/** The unsaved changes of the origin table, kept while the Table tab shows the referenced table. */
export interface PickStash {
  changes: Record<string, Record<string, string>>;
  files: Record<string, Record<string, File[]>>;
  refTexts: Record<string, string>;
  /** The row whose record dialog was open when the picker started: it opens again when the Table tab comes back. */
  reopen?: string;
}

/** The record chosen: its key, shown to the cell as `text`. */
export interface PickResult {
  origin: PickOrigin;
  value: string;
  text: string;
}

interface RefPickValue {
  /** Set while a record is being chosen in the referenced table. */
  active: { origin: PickOrigin; target: PickTarget } | null;
  start: (origin: PickOrigin, target: PickTarget, stash: PickStash) => void;
  pick: (value: string, text: string) => void;
  cancel: () => void;
  /** Reads (and forgets) what the origin table left when it was left. */
  takeStash: (database: string, table: string) => PickStash | null;
  /** Reads (and forgets) the record chosen for the origin table, if any. */
  takeResult: (database: string, table: string) => PickResult | null;
}

const RefPickContext = createContext<RefPickValue | null>(null);

/** The record picker of the Table tab, or null where there is none. */
export function useRefPick(): RefPickValue | null {
  return useContext(RefPickContext);
}

const keyOf = (database: string, table: string) => `${database}/${table}`;

/** Gives the Table tab the record picker: it switches to the referenced table (in the app that owns it), and comes back to the origin
 * with the record chosen. */
export function RefPickHost({ children }: { children: ReactNode }) {
  const selection = useDatabaseSelection();
  const [active, setActive] = useState<RefPickValue["active"]>(null);
  const [stashes, setStashes] = useState<Record<string, PickStash>>({});
  const [results, setResults] = useState<Record<string, PickResult>>({});

  const goBack = useCallback((origin: PickOrigin) => {
    selection?.choose(origin.database, origin.table);
  }, [selection]);

  const start = useCallback((origin: PickOrigin, target: PickTarget, stash: PickStash) => {
    setStashes((current) => ({ ...current, [keyOf(origin.database, origin.table)]: stash }));
    setActive({ origin, target });
    selection?.choose(target.database, target.table);
  }, [selection]);

  const pick = useCallback((value: string, text: string) => {
    if (!active) return;
    setResults((current) => ({ ...current, [keyOf(active.origin.database, active.origin.table)]: { origin: active.origin, value, text } }));
    setActive(null);
    goBack(active.origin);
  }, [active, goBack]);

  const cancel = useCallback(() => {
    if (!active) return;
    setActive(null);
    goBack(active.origin);
  }, [active, goBack]);

  const takeStash = useCallback((database: string, table: string) => {
    const found = stashes[keyOf(database, table)] ?? null;
    if (found) setStashes((current) => { const next = { ...current }; delete next[keyOf(database, table)]; return next; });
    return found;
  }, [stashes]);

  const takeResult = useCallback((database: string, table: string) => {
    const found = results[keyOf(database, table)] ?? null;
    if (found) setResults((current) => { const next = { ...current }; delete next[keyOf(database, table)]; return next; });
    return found;
  }, [results]);

  const value = useMemo<RefPickValue>(() => ({ active, start, pick, cancel, takeStash, takeResult }), [active, start, pick, cancel, takeStash, takeResult]);
  return <RefPickContext.Provider value={value}>{children}</RefPickContext.Provider>;
}
