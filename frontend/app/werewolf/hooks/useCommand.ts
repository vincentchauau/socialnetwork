"use client";

import { useCallback, useRef, useState } from "react";

import { errorText } from "../lib/errors";

/** Runs one command at a time: busy flag, double-submit guard, errors mapped to a Vietnamese toast text. */
export function useCommand(notify: (text: string) => void) {
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);

  const run = useCallback(
    async <T,>(command: () => Promise<T>): Promise<T | undefined> => {
      if (busyRef.current) return undefined;
      busyRef.current = true;
      setBusy(true);
      try {
        return await command();
      } catch (error) {
        notify(errorText(error));
        return undefined;
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [notify],
  );

  return { busy, run };
}
