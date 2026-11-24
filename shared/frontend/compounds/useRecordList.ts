"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../api";
import { type Labels, type Row, detailText } from "./crudModel";
import { mergeLabels } from "./galleryModel";

export interface UseRecordListOptions {
  /** The address of the table in an admin-style API, e.g. "/api/database/app/app/admin/photos". */
  base: string;
  /** The query string of the list request (search, offset, limit, sort, filters): the rows are read again when it changes. */
  query: string;
  /** The rows are added after the ones already read (the next batch of a growing list) instead of replacing them (a page). */
  append?: boolean;
  /** False while what the request needs (the table's description, the session) is still being asked for. */
  ready?: boolean;
}

/**
 * Reading, picking and deleting the rows of one table, the same for the table and the grid of cards: the rows of the page with their labels
 * and the count, a way to read them again, the keys that are picked, and deleting one or many. What is shown is up to the caller.
 */
export function useRecordList({ base, query, append = false, ready = true }: UseRecordListOptions) {
  const [rows, setRows] = useState<Row[]>([]);
  const [labels, setLabels] = useState<Labels>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [picked, setPicked] = useState<ReadonlySet<string | number>>(new Set());
  const [bulkAsking, setBulkAsking] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setLoading(true);
    apiFetch<{ total: number; rows: Row[]; labels?: Labels }>(`${base}?${query}`)
      .then((page) => {
        if (cancelled) return;
        setRows((previous) => (append ? [...previous, ...page.rows] : page.rows));
        setLabels((previous) => (append ? mergeLabels(previous, page.labels) : (page.labels ?? {})));
        if (!append) setPicked(new Set());
        setTotal(page.total);
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(detailText(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, base, query, version]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);

  /** Deletes the rows with these keys one by one; a failure stops there and shows its words. True when all went. */
  async function deleteKeys(keys: (string | number)[]): Promise<boolean> {
    try {
      for (const key of keys) await apiFetch(`${base}/${key}`, { method: "DELETE" });
      setLoadError(null);
      return true;
    } catch (error) {
      setLoadError(detailText(error));
      return false;
    }
  }

  /** Deletes the picked rows (the caller asked first) and reads the rows again. */
  async function removePicked() {
    setBulkAsking(false);
    const keys = [...picked];
    setPicked(new Set());
    await deleteKeys(keys);
    reload();
  }

  return { rows, setRows, labels, total, loading, loadError, setLoadError, picked, setPicked, bulkAsking, setBulkAsking, reload, deleteKeys, removePicked };
}
