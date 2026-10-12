"use client";

import { useCallback, useRef, useState } from "react";

import { errorText } from "../lib/auth";

/** Busy flag + error/success text for one form action, with a guard against double submits. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const busyRef = useRef(false);

  const run = useCallback(async (action: () => Promise<string | void>): Promise<boolean> => {
    if (busyRef.current) return false;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const text = await action();
      if (text) setMessage(text);
      return true;
    } catch (caught) {
      setError(errorText(caught));
      return false;
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, []);

  const fail = useCallback((text: string) => {
    setMessage(null);
    setError(text);
  }, []);

  return { busy, error, message, run, fail };
}
