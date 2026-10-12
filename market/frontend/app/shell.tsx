"use client";

import Link from "next/link";
import { ReactNode, useCallback, useEffect, useState } from "react";

import { User, loadSession } from "@sn/api";

type Auth =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error" }
  | { status: "signed-in"; user: User };

/** Page frame: auth gate (loading / error / sign-in link), heading, home link and navigation. */
export function Shell({
  title,
  children,
}: {
  title: string;
  children: (user: User) => ReactNode;
}) {
  const [auth, setAuth] = useState<Auth>({ status: "loading" });

  useEffect(() => {
    loadSession()
      .then((user) => setAuth(user ? { status: "signed-in", user } : { status: "anonymous" }))
      .catch(() => setAuth({ status: "error" }));
  }, []);

  return (
    <div className="stack">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
        <h1 style={{ margin: 0 }}>{title}</h1>
        <a href="/">← Home</a>
      </div>
      <nav aria-label="Market" className="row" style={{ flexWrap: "wrap" }}>
        <Link href="/">Shop</Link>
        <Link href="/cart">Cart</Link>
        <Link href="/orders">My orders</Link>
        <Link href="/sell">Sell</Link>
      </nav>
      {auth.status === "loading" && <p className="muted">Loading…</p>}
      {auth.status === "error" && (
        <p role="alert" className="error">
          Could not reach the server. Please try again.
        </p>
      )}
      {auth.status === "anonymous" && (
        <p>
          Please <a href="/login">sign in</a> first.
        </p>
      )}
      {auth.status === "signed-in" && children(auth.user)}
    </div>
  );
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

export function ErrorLine({ message }: { message: string | null }) {
  return message ? (
    <p role="alert" className="error">
      {message}
    </p>
  ) : null;
}
