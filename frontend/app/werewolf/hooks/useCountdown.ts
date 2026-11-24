"use client";

import { useEffect, useRef, useState } from "react";

const TICK_MS = 500;

/**
 * Seconds left for a server snapshot `{total, secondsLeft}`: the server only sends the value when the
 * state changes, so the countdown runs locally from the moment the snapshot arrived.
 */
export function useCountdown(timer: { total: number; secondsLeft: number } | null): number | null {
  const received = useRef({ at: Date.now(), left: timer?.secondsLeft ?? 0 });
  const [, setTick] = useState(0);

  useEffect(() => {
    received.current = { at: Date.now(), left: timer?.secondsLeft ?? 0 };
    setTick((n) => n + 1);
  }, [timer?.secondsLeft, timer?.total]);

  const active = timer !== null;
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => setTick((n) => n + 1), TICK_MS);
    return () => clearInterval(id);
  }, [active]);

  if (!timer) return null;
  return Math.max(0, received.current.left - (Date.now() - received.current.at) / 1000);
}
