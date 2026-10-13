"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Calls `task` repeatedly: the next run is scheduled only after the previous one settled (no overlap),
 * pauses while the tab is hidden, runs at once when it becomes visible again and stops on unmount.
 * `task` must handle its own errors. Returns `refresh`, which runs the task now unless one is running.
 */
export function usePolling(task: () => Promise<void>, intervalMs: number): () => void {
  const taskRef = useRef(task);
  const intervalRef = useRef(intervalMs);
  const tickRef = useRef<() => void>(() => {});
  const rescheduleRef = useRef<() => void>(() => {});
  taskRef.current = task;
  intervalRef.current = intervalMs;

  useEffect(() => {
    let stopped = false;
    let running = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const schedule = () => {
      clearTimeout(timer);
      timer = undefined;
      if (!stopped && !document.hidden) timer = setTimeout(tick, intervalRef.current);
    };
    const tick = () => {
      if (stopped || running) return;
      clearTimeout(timer);
      running = true;
      void taskRef.current().finally(() => {
        running = false;
        schedule();
      });
    };
    const onVisibility = () => {
      if (document.hidden) clearTimeout(timer);
      else tick();
    };

    tickRef.current = tick;
    // The interval may change right after a run (new data); re-arm a waiting timer with it.
    rescheduleRef.current = () => {
      if (timer !== undefined && !running) schedule();
    };
    document.addEventListener("visibilitychange", onVisibility);
    onVisibility();
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  useEffect(() => rescheduleRef.current(), [intervalMs]);

  return useCallback(() => tickRef.current(), []);
}
