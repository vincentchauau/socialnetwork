"use client";

import { type KeyboardEvent, useEffect, useRef } from "react";

export interface ContextMenuItem {
  key: string;
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
}

export interface ContextMenuProps {
  /** Where the menu opens, in window pixels (the place of the right click). */
  x: number;
  y: number;
  label: string;
  items: readonly ContextMenuItem[];
  onClose: () => void;
}

/** A small menu at a point, opened by a right click: it closes on a choice, on Escape and on a click elsewhere. */
export default function ContextMenu({ x, y, label, items, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const close = (event: Event) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("contextmenu", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("contextmenu", close);
    };
  }, [onClose]);

  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key === "Escape") onClose();
  };

  return (
    <ul
      ref={ref}
      role="menu"
      aria-label={label}
      onKeyDown={onKeyDown}
      style={{
        position: "fixed", left: x, top: y, zIndex: 80, listStyle: "none", margin: 0, padding: 4, minWidth: 180,
        background: "var(--solid-0, #ffffff)", border: "1px solid color-mix(in srgb, var(--line, #16181d) 30%, transparent)",
        borderRadius: 8,
      }}
    >
      {items.map((item) => (
        <li key={item.key} role="none">
          <button
            type="button"
            role="menuitem"
            disabled={item.disabled}
            onClick={() => {
              onClose();
              item.onSelect();
            }}
            style={{
              display: "block", width: "100%", textAlign: "left", padding: "6px 12px", border: 0, borderRadius: 6,
              background: "transparent", color: item.danger ? "#b42318" : "inherit", cursor: item.disabled ? "default" : "pointer",
              opacity: item.disabled ? 0.5 : 1, font: "inherit",
            }}
          >
            {item.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
