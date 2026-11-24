"use client";

import { reauthRequired } from "@sn/api";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

import ReauthDialog, { REAUTH_CANCELLED } from "../components/ReauthDialog";

interface Pending {
  methods: string[];
  settle: (ok: boolean) => void;
}

/**
 * `withReauth(action)` runs a sensitive action; if the server answers "re-authentication required"
 * it opens the dialog, and after a successful proof retries the action exactly once.
 * Render `dialog` somewhere in the component. A cancelled dialog rejects with a plain Error.
 */
export function useReauth(): { withReauth: <T>(action: () => Promise<T>) => Promise<T>; dialog: ReactNode } {
  const [pending, setPending] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);

  useEffect(() => () => pendingRef.current?.settle(false), []);

  const withReauth = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    try {
      return await action();
    } catch (error) {
      const methods = reauthRequired(error);
      if (!methods) throw error;
      const ok = await new Promise<boolean>((resolve) => {
        const entry: Pending = {
          methods,
          settle: (value) => {
            pendingRef.current = null;
            setPending(null);
            resolve(value);
          },
        };
        pendingRef.current = entry;
        setPending(entry);
      });
      if (!ok) throw new Error(REAUTH_CANCELLED);
      return action();
    }
  }, []);

  const dialog = pending ? (
    <ReauthDialog methods={pending.methods} onSuccess={() => pending.settle(true)} onCancel={() => pending.settle(false)} />
  ) : null;

  return { withReauth, dialog };
}
