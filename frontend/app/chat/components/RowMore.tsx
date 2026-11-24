"use client";

import { useRef, useState, type CSSProperties, type ReactNode } from "react";

import Button from "@sn/elements/Button";
import { tr } from "../i18n";

const CLOSE_DELAY_MS = 250;

/** The actions of a row stay out of sight: "More" opens them as a menu that floats over the table (fixed, so no column clips it) and closes when the pointer or the focus leaves it, or on Escape. */
export default function RowMore({ label, children }: { label: string; children: ReactNode }) {
  const [at, setAt] = useState<{ top: number; right: number } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const button = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const keep = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  const leave = () => {
    keep();
    timer.current = setTimeout(() => setAt(null), CLOSE_DELAY_MS);
  };
  const toggle = () => {
    keep();
    if (at) return setAt(null);
    const box = button.current?.getBoundingClientRect();
    if (box) setAt({ top: box.bottom + 2, right: window.innerWidth - box.right });
  };
  const style: CSSProperties = {
    position: "fixed", zIndex: 1000, display: "flex", flexDirection: "column", alignItems: "stretch", gap: 6, padding: 8, width: "max-content", minWidth: 120, whiteSpace: "nowrap",
    background: "var(--solid-0)", border: "1px solid var(--line)", borderRadius: 8, ...at,
  };
  const outside = (event: React.FocusEvent) => {
    const next = event.relatedTarget as Node | null;
    if (!next || !(button.current?.contains(next) || menu.current?.contains(next))) setAt(null);
  };
  return (
    <div ref={button} style={{ display: "flex", justifyContent: "flex-end" }} onMouseEnter={keep} onMouseLeave={leave} onBlur={outside} onKeyDown={(event) => event.key === "Escape" && setAt(null)}>
      <Button type="button" size="sm" variant="ghost" aria-expanded={at !== null} aria-haspopup="menu" aria-label={`${tr("rm_xem_them")} ${label}`} onClick={toggle}>
        ⋯
      </Button>
      {at && <div ref={menu} role="menu" aria-label={label} style={style}>{children}</div>}
    </div>
  );
}
