"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface Page<T, C> {
  items: T[];
  next_cursor: C | null;
}

export interface PagedList<T> {
  items: T[];
  /** The first page is on its way. */
  loading: boolean;
  /** Another page is on its way. */
  loadingMore: boolean;
  error: string | null;
  hasMore: boolean;
  loadMore: () => void;
  reload: () => void;
}

/**
 * A list read page by page with a cursor, from the first page again whenever `deps` change (the filters), and one more page on `loadMore`.
 * A reply that comes after the filters changed again is dropped. `describe` turns a failure into the line the person reads.
 */
export function usePagedList<T, C extends string | number>(
  load: (cursor: C | null) => Promise<Page<T, C>>,
  deps: readonly unknown[],
  describe: (failure: unknown) => string,
): PagedList<T> {
  const [items, setItems] = useState<T[]>([]);
  const [cursor, setCursor] = useState<C | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const generation = useRef(0);
  const loadRef = useRef(load);
  loadRef.current = load;
  const describeRef = useRef(describe);
  describeRef.current = describe;

  useEffect(() => {
    const mine = ++generation.current;
    setLoading(true);
    setError(null);
    loadRef
      .current(null)
      .then((page) => {
        if (mine !== generation.current) return;
        setItems(page.items);
        setCursor(page.next_cursor);
      })
      .catch((failure: unknown) => {
        if (mine === generation.current) setError(describeRef.current(failure));
      })
      .finally(() => {
        if (mine === generation.current) setLoading(false);
      });
    return () => {
      generation.current += 1; // whatever is still on its way is not wanted any more
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const loadMore = useCallback(() => {
    if (cursor === null) return;
    const mine = generation.current;
    setLoadingMore(true);
    setError(null);
    loadRef
      .current(cursor)
      .then((page) => {
        if (mine !== generation.current) return;
        setItems((current) => [...current, ...page.items]);
        setCursor(page.next_cursor);
      })
      .catch((failure: unknown) => {
        if (mine === generation.current) setError(describeRef.current(failure));
      })
      .finally(() => {
        if (mine === generation.current) setLoadingMore(false);
      });
  }, [cursor]);

  return { items, loading, loadingMore, error, hasMore: cursor !== null, loadMore, reload: useCallback(() => setTick((value) => value + 1), []) };
}

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (value: T | null) => void;
}

/** Runs `load` on mount and whenever it changes; ignores results from stale runs. */
export function useLoad<T>(load: () => Promise<T>, describe: (error: unknown) => string): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    load()
      .then((value) => {
        if (cancelled) return;
        setData(value);
        setError(null);
      })
      .catch((failure: unknown) => {
        if (!cancelled) setError(describe(failure));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { data, error, loading, reload, setData };
}

/** True once the page is known to sit inside a frame of the site (a detail page opened in the User pane), which then drops its own bar and chat. */
export function useFramed(): boolean {
  const [framed, setFramed] = useState(false);
  useEffect(() => {
    try {
      setFramed(window.self !== window.top);
    } catch {
      setFramed(true); // a parent we cannot reach is a frame all the same
    }
  }, []);
  return framed;
}
