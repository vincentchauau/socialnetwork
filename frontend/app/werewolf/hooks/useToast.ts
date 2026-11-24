"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const TOAST_MS = 6_000;

/** One toast message at a time; it clears itself after a few seconds. */
export function useToast() {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setMessage(null);
  }, []);

  const notify = useCallback(
    (text: string) => {
      if (timer.current) clearTimeout(timer.current);
      setMessage(text);
      timer.current = setTimeout(dismiss, TOAST_MS);
    },
    [dismiss],
  );

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return { message, notify, dismiss };
}
