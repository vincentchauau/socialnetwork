"use client";

import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

/** One form that can be applied from the page's single "Đổi tài khoản" button. */
type Applier = () => Promise<boolean>;

interface AccountChangesValue {
  /** True under the account page: forms leave their apply button to the page's one button. */
  batched: boolean;
  /** The forms that hold something to apply, id -> label, in the order they were reported. */
  pending: Record<string, string>;
  register: (id: string, apply: Applier) => () => void;
  report: (id: string, label: string, dirty: boolean) => void;
  /**
   * Applies every pending form in `order`, one after the other, and stops at the first that fails.
   * `failed` is the id of that form, so the page can open its tab where its own message is shown.
   */
  applyAll: (order: readonly string[]) => Promise<{ applied: string[]; failed?: string }>;
}

const AccountChangesContext = createContext<AccountChangesValue | null>(null);

/**
 * Collects the changes a user has typed or recorded in the tabs. Each form keeps its own state, its own button and its
 * own messages; this only lets one button on the page apply the ones that are filled in.
 */
export function AccountChangesProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Record<string, string>>({});
  const appliers = useRef(new Map<string, Applier>());
  const pendingRef = useRef(pending);
  pendingRef.current = pending;

  const register = useCallback((id: string, apply: Applier) => {
    appliers.current.set(id, apply);
    return () => {
      appliers.current.delete(id);
      setPending(({ [id]: _gone, ...rest }) => rest);
    };
  }, []);

  const report = useCallback((id: string, label: string, dirty: boolean) => {
    setPending((current) => {
      if (dirty) return current[id] === label ? current : { ...current, [id]: label };
      if (!(id in current)) return current;
      const { [id]: _gone, ...rest } = current;
      return rest;
    });
  }, []);

  const applyAll = useCallback(async (order: readonly string[]) => {
    const applied: string[] = [];
    for (const id of order) {
      if (!(id in pendingRef.current)) continue;
      const apply = appliers.current.get(id);
      if (!apply) continue;
      if (!(await apply())) return { applied, failed: id };
      applied.push(id);
    }
    return { applied };
  }, []);

  const value = useMemo(() => ({ batched: true, pending, register, report, applyAll }), [pending, register, report, applyAll]);
  return <AccountChangesContext.Provider value={value}>{children}</AccountChangesContext.Provider>;
}

/** The page's pending changes and the way to apply them; empty outside a provider. */
export function useAccountChanges(): AccountChangesValue {
  const value = useContext(AccountChangesContext);
  return value ?? { batched: false, pending: {}, register: () => () => undefined, report: () => undefined, applyAll: async () => ({ applied: [] }) };
}

/**
 * Offers a form to the page's "Đổi tài khoản" button. `apply` runs the same code as the form's own submit and says
 * whether it worked; it may use the form's latest state because the newest closure is always the one called.
 */
export function useAccountChange(id: string, label: string, dirty: boolean, apply: Applier): void {
  const { register, report } = useAccountChanges();
  const latest = useRef(apply);
  latest.current = apply;
  useEffect(() => register(id, () => latest.current()), [id, register]);
  useEffect(() => report(id, label, dirty), [id, label, dirty, report]);
}
