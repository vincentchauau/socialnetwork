"use client";

import { useCallback, useEffect, useState } from "react";

/** Counts down whole seconds after start(); `left` is 0 when the action may be repeated. */
export function useCooldown() {
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (left <= 0) return;
    const timer = window.setTimeout(() => setLeft((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [left]);

  const start = useCallback((seconds: number) => setLeft(seconds), []);
  return { left, start };
}
