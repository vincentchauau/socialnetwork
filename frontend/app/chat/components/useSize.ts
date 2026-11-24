"use client";

import { useEffect, useState } from "react";

/** The width of an element, and the height it has left in the page pane it sits in (the scrolling area above the chat), kept up to date. */
export function useSize<T extends HTMLElement>() {
  // A ref callback, not a ref object: the size is measured when the element appears, not once at mount.
  const [element, setElement] = useState<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!element) return;
    // The page pane is the nearest scrolling area: its height is the room the element has.
    const pane = element.closest<HTMLElement>('[style*="overflow: auto"]');
    const update = () => {
      const room = pane ? pane.clientHeight - (element.getBoundingClientRect().top - pane.getBoundingClientRect().top) - 8 : 0;
      setSize({ width: element.clientWidth, height: Math.max(0, room) });
    };
    update();
    // Without ResizeObserver (old browsers, jsdom) the size is read once, at the start.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    if (pane) observer.observe(pane);
    return () => observer.disconnect();
  }, [element]);
  return [setElement, size] as const;
}
