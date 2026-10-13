"use client";

import { useEffect, useState } from "react";

export type UrlToken = { ready: false } | { ready: true; token: string | null };

/** `#token=...` (preferred) or, for mails sent before the change, `?token=...`; never trimmed or decoded twice. */
export function parseToken(hash: string, search: string): string | null {
  const fromHash = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  if (fromHash) return fromHash;
  return new URLSearchParams(search).get("token") || null;
}

/**
 * Reads `token` from the URL fragment (fallback: the query string) once, then clears both from the address bar
 * (history.replaceState) so the secret stays only in memory: never in a request URL, the history entry or a log.
 * A fragment is never sent to the server, so it cannot reach logs or Referer headers.
 */
export function useUrlToken(): UrlToken {
  const [state, setState] = useState<UrlToken>({ ready: false });

  useEffect(() => {
    const { hash, search, pathname } = window.location;
    const token = parseToken(hash, search);
    if (hash || search) window.history.replaceState(window.history.state, "", pathname);
    setState({ ready: true, token });
  }, []);

  return state;
}

export type FragmentValue = { ready: false } | { ready: true; value: string | null };

/** One `name=value` pair of the URL fragment (`#r=abc`), or null. Never read from the query string. */
export function parseFragmentParam(hash: string, name: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, "")).get(name) || null;
}

/** Reads `#name=value` once and clears the fragment from the address bar, like useUrlToken. */
export function useFragmentParam(name: string): FragmentValue {
  const [state, setState] = useState<FragmentValue>({ ready: false });

  useEffect(() => {
    const { hash, search, pathname } = window.location;
    const value = parseFragmentParam(hash, name);
    if (hash) window.history.replaceState(window.history.state, "", pathname + search);
    setState({ ready: true, value });
  }, [name]);

  return state;
}
