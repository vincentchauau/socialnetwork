"use client";

import { type CSSProperties, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";
import Button from "../elements/Button";
import TreeView, { type TreeNode } from "./TreeView";

/** A pane the app adds beside its page (hidden unless `defaultVisible`). */
export interface ExtraPane {
  key: string;
  label: string;
  title?: string;
  node: ReactNode;
  defaultVisible?: boolean;
}

export interface SplitPane {
  /** Names the pane: in the map of what is shown, in the storage and in what `onVisibleChange` says. */
  key: string;
  /** The text of the button that shows and hides the pane. A split where no pane has one has no buttons. */
  label?: string;
  /** A tooltip for the button of the pane. */
  title?: string;
  node: ReactNode;
  /** Shown at first (the default), unless `visible` says otherwise. */
  defaultVisible?: boolean;
  /** Keep what is in the pane alive while it is hidden (its state survives); by default a hidden pane is not rendered at all. */
  keepMounted?: boolean;
  /** Its share of the room, relative to the other panes. */
  weight?: number;
  /** The least size of the pane in pixels (height in a vertical split, width in a horizontal one). */
  minSize?: number;
  /** The pane takes only the room its content needs, and has no share of its own. */
  fit?: boolean;
}

/** What goes under the row of buttons: as it is, or made from the keys of the panes that are shown (a chooser that matters to some panes only). */
export type SplitToolbar = ReactNode | ((shown: string[]) => ReactNode);

export interface SplitPanelProps {
  panes: SplitPane[];
  orientation?: "horizontal" | "vertical";
  /** The name of the group of buttons, and of the split for people who cannot see it. */
  label?: string;
  /** The name of every divider. */
  resizeLabel?: string;
  /** Which panes are shown, by key, when the owner of the split keeps that state (then also pass `onVisibleChange`). */
  visible?: Record<string, boolean>;
  onVisibleChange?: (next: Record<string, boolean>) => void;
  /** Remember what is shown, per person, under this key of the browser storage (when `visible` is not kept by the owner). */
  storageKey?: string;
  /** Something the owner puts under the row of buttons (a chooser for what the panes show). */
  toolbar?: SplitToolbar;
  /** Something on the same row as the buttons, after them (the name of the room, say). */
  header?: ReactNode;
}

const HANDLE = 8;
const KEY_STEP = 24;
const DEFAULT_MIN = 120;

function storedSizes(key: string): Record<string, number> {
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    return Object.fromEntries(Object.entries(parsed).filter(([, value]) => typeof value === "number" && Number.isFinite(value) && value > 0)) as Record<string, number>;
  } catch {
    return {};
  }
}

function stored(key: string | undefined): Record<string, boolean> {
  if (!key) return {};
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

/**
 * A row (or a column) of any number of panes with a draggable, keyboard-operable divider between each two that are shown, and over it one
 * button per labelled pane that shows and hides that pane. Sizes are weights kept in state, so a pane that is hidden and shown again keeps
 * its share, and no pane is smaller than its `minSize`. Splits nest: a pane can hold another split with buttons of its own.
 */
export default function SplitPanel({ panes, orientation = "horizontal", label = "Panels", resizeLabel = "Resize", visible, onVisibleChange, storageKey, toolbar, header }: SplitPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const stopDrag = useRef<(() => void) | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [own, setOwn] = useState<Record<string, boolean>>({});
  const horizontal = orientation === "horizontal";

  useEffect(() => {
    setOwn(stored(storageKey));
    if (storageKey) setWeights(storedSizes(`${storageKey}:sizes`));
  }, [storageKey]);
  // A divider that is being dragged when the panel goes away lets go of the window.
  useEffect(() => () => stopDrag.current?.(), []);

  const isShown = (pane: SplitPane): boolean => (visible ?? own)[pane.key] ?? pane.defaultVisible ?? true;
  const shown = panes.filter(isShown);
  const bar = typeof toolbar === "function" ? toolbar(shown.map((pane) => pane.key)) : toolbar;
  const weightOf = (pane: SplitPane) => weights[pane.key] ?? pane.weight ?? 1;
  const minOf = (pane: SplitPane) => pane.minSize ?? DEFAULT_MIN;
  const sized = shown.filter((pane) => !pane.fit);

  // Somebody asks for a pane to be shown (the meeting button of a room asks for the User pane): `sn:show-pane` with `{ key }`.
  useEffect(() => {  // (subscribed again each render, so it sees what is shown now)
    const onShow = (event: Event) => {
      const key = (event as CustomEvent<{ key?: string }>).detail?.key;
      const pane = panes.find((candidate) => candidate.key === key);
      if (pane && !isShown(pane)) toggle(pane.key);
    };
    window.addEventListener("sn:show-pane", onShow);
    return () => window.removeEventListener("sn:show-pane", onShow);
  });

  function toggle(key: string) {
    const next = Object.fromEntries(panes.map((pane) => [pane.key, pane.key === key ? !isShown(pane) : isShown(pane)]));
    if (visible === undefined) {
      setOwn(next);
      if (storageKey) {
        try {
          window.localStorage.setItem(storageKey, JSON.stringify(next));
        } catch {
          // not remembered: fine
        }
      }
    }
    onVisibleChange?.(next);
  }

  /** Move the divider after pane `index` (among the shown ones) by `delta` pixels. */
  function move(index: number, delta: number, base: Record<string, number>) {
    const box = ref.current?.getBoundingClientRect();
    const first = shown[index];
    const second = shown[index + 1];
    if (!box || first.fit || second.fit) return;
    const room = (horizontal ? box.width : box.height) - HANDLE * (shown.length - 1);
    if (room <= 0) return;
    const total = sized.reduce((sum, pane) => sum + (base[pane.key] ?? pane.weight ?? 1), 0);
    const perPixel = total / room;
    const a = base[first.key] ?? first.weight ?? 1;
    const b = base[second.key] ?? second.weight ?? 1;
    const shift = Math.max(-(a - minOf(first) * perPixel), Math.min(b - minOf(second) * perPixel, delta * perPixel));
    setWeights((current) => {
      const next = { ...current, ...base, [first.key]: a + shift, [second.key]: b - shift };
      if (storageKey) {
        try {
          window.localStorage.setItem(`${storageKey}:sizes`, JSON.stringify(next));
        } catch {
          // not remembered: fine
        }
      }
      return next;
    });
  }

  const baseWeights = () => Object.fromEntries(shown.map((pane) => [pane.key, weightOf(pane)]));

  function drag(index: number, event: PointerEvent) {
    event.preventDefault();
    const start = horizontal ? event.clientX : event.clientY;
    const base = baseWeights();
    const onMove = (to: globalThis.PointerEvent) => move(index, (horizontal ? to.clientX : to.clientY) - start, base);
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      stopDrag.current = null;
    };
    stopDrag.current = onUp;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function press(index: number, event: KeyboardEvent) {
    const back = horizontal ? "ArrowLeft" : "ArrowUp";
    const forward = horizontal ? "ArrowRight" : "ArrowDown";
    if (event.key !== back && event.key !== forward) return;
    event.preventDefault();
    move(index, event.key === forward ? KEY_STEP : -KEY_STEP, baseWeights());
  }

  const tracks = shown
    .flatMap((pane, index) => [pane.fit ? "auto" : `minmax(${minOf(pane)}px, ${weightOf(pane)}fr)`, ...(index < shown.length - 1 ? [`${HANDLE}px`] : [])])
    .join(" ");
  const layout: CSSProperties = { display: "grid", flex: "1 1 0", width: "100%", minWidth: 0, minHeight: 0, [horizontal ? "gridTemplateColumns" : "gridTemplateRows"]: tracks };
  const handleStyle: CSSProperties = { background: "color-mix(in srgb, var(--line) 30%, transparent)", cursor: horizontal ? "col-resize" : "row-resize", touchAction: "none" };
  const labelled = panes.filter((pane) => pane.label);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", minWidth: 0, minHeight: 0 }}>
      {labelled.length > 0 && (
        <div role="toolbar" aria-label={label} style={{ display: "flex", gap: 8, padding: "6px 8px", alignItems: "center", flexWrap: "wrap", flex: "0 0 auto" }}>
          {labelled.map((pane) => {
            const on = isShown(pane);
            return (
              <Button
                key={pane.key}
                type="button"
                size="sm"
                variant={on ? "primary" : "secondary"}
                aria-pressed={on}
                title={pane.title}
                onClick={() => toggle(pane.key)}
                style={{ flex: "0 0 auto", borderBottom: on ? "3px solid currentColor" : "3px solid transparent", outline: on ? "none" : "1px dashed currentColor", outlineOffset: -3 }}
              >
                {pane.label}
              </Button>
            );
          })}
          {header ? <span style={{ display: "inline-flex", alignItems: "center", gap: 8, marginLeft: 8, minWidth: 0 }}>{header}</span> : null}
        </div>
      )}
      {bar && <div style={{ padding: "0 8px 6px", flex: "0 0 auto" }}>{bar}</div>}
      <div ref={ref} style={layout}>
        {panes.flatMap((pane) => {
          const index = shown.indexOf(pane);
          const on = index >= 0;
          const items: ReactNode[] = [];
          if (on || pane.keepMounted) {
            items.push(
              <div key={pane.key} style={{ display: on ? "block" : "none", minWidth: 0, minHeight: 0, overflow: "auto" }}>
                {pane.node}
              </div>,
            );
          }
          if (on && index < shown.length - 1) {
            items.push(
              <div
                key={`${pane.key}:handle`}
                role="separator"
                tabIndex={0}
                aria-label={resizeLabel}
                aria-orientation={horizontal ? "vertical" : "horizontal"}
                onPointerDown={(event) => drag(index, event)}
                onKeyDown={(event) => press(index, event)}
                style={handleStyle}
              />,
            );
          }
          return items;
        })}
      </div>
    </div>
  );
}

export { SplitPanel };

export interface FacetGridViewProps {
  /** Remembers, per person, what is shown and how wide: one name per page. */
  name: string;
  filtersLabel: string;
  resultsLabel: string;
  /** The left side: the tree and the fields that narrow the results. */
  filters: ReactNode;
  /** The right side: what was found. */
  children: ReactNode;
}

const PANE: React.CSSProperties = { height: "100%", minHeight: 0, overflow: "auto", padding: 8, boxSizing: "border-box" };

/** The way every catalogue looks: the filters on the left, the results on the right, each hidden or resized as the person likes. */
export function FacetGridView({ name, filtersLabel, resultsLabel, filters, children }: FacetGridViewProps) {
  return (
    // the split fills its parent: a parent with no height of its own (the User pane) would leave it no room, so it gets one
    // down to the bottom of the window (the bar of the site and the tabs above take about 190px)
    <div style={{ height: "calc(100dvh - 190px)", minHeight: 320 }}>
    <SplitPanel
      label={name}
      storageKey={`sn_browse_${name}`}
      panes={[
        { key: "filters", label: filtersLabel, node: <div style={PANE}>{filters}</div>, weight: 1, minSize: 180 },
        { key: "results", label: resultsLabel, node: <div style={PANE}>{children}</div>, weight: 3, minSize: 280, keepMounted: true },
      ]}
    />
    </div>
  );
}

// ---- tabs (a single choice of several panels, the tab bar above them) ----
export interface TabPanelProps {
  /** The tab bar. A node without children is a tab (its `key` picks its panel); a node with children is a group: a drop-down of tabs. */
  data: readonly TreeNode[];
  /** Content per tab key. Every panel stays mounted (hidden when inactive) so its state survives switching. */
  panels: Record<string, ReactNode>;
  /** Controlled tab; omit to let TabPanel keep its own selection (first tab to begin with). */
  activeKey?: string;
  onChange?: (key: string) => void;
  /** Extra `#hash` targets that open a tab: `{ "change-password": "password" }` opens tab `password` and scrolls to `#change-password`. */
  aliases?: Record<string, string>;
  /**
   * Keep every panel mounted and only hide the inactive ones (default), so their state survives switching. Pass false
   * when a panel has side effects on mount (a camera, a poll, a script): then only the open tab's panel is built.
   */
  keepMounted?: boolean;
  /** Names the <nav> landmark around the tree. */
  "aria-label": string;
}

function leafKeys(nodes: readonly TreeNode[]): string[] {
  return nodes.flatMap((node) => (node.children?.length ? leafKeys(node.children) : [node.key]));
}

// A tab is a real link to `#key`, so it works without script, can be bookmarked and the browser's Back button steps through tabs.
function withHashLinks(nodes: readonly TreeNode[]): TreeNode[] {
  return nodes.map((node) =>
    node.children?.length ? { ...node, children: withHashLinks(node.children) } : { ...node, href: `#${node.key}` },
  );
}

/** A tab panel whose tab bar is the horizontal `TreeView` (a group is a drop-down of its tabs), with the selected panel below. */
export function TabPanel({ data, panels, activeKey, onChange, aliases, keepMounted = true, ...rest }: TabPanelProps) {
  const keys = leafKeys(data);
  const [localActive, setLocalActive] = useState(keys[0]);
  // A tab that is no longer in `data` (a mode dropped it) falls back to the first one.
  const wanted = activeKey ?? localActive;
  const active = keys.includes(wanted) ? wanted : keys[0];
  const scrollTarget = useRef<string | null>(null);

  function select(key: string) {
    setLocalActive(key);
    onChange?.(key);
  }

  // Resolve `#hash` (also on load and on Back/Forward) to a tab: a tab key, or an alias for a spot inside a tab.
  const aliasSignature = JSON.stringify(aliases ?? {});
  const keySignature = keys.join("|");
  useEffect(() => {
    const known = new Set(keySignature.split("|"));
    const table: Record<string, string> = JSON.parse(aliasSignature);
    function read() {
      const id = decodeURIComponent(window.location.hash.slice(1));
      const key = known.has(id) ? id : table[id];
      if (!key) return;
      if (key !== id) scrollTarget.current = id;
      setLocalActive(key);
      onChange?.(key);
    }
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
    // onChange is deliberately left out: a parent passing a new function each render must not re-read the hash.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aliasSignature, keySignature]);

  // The alias target sat in a hidden panel when the browser tried to scroll to it; do it once the panel shows.
  useEffect(() => {
    const id = scrollTarget.current;
    if (id === null) return;
    scrollTarget.current = null;
    document.getElementById(id)?.scrollIntoView?.();
  }, [active]);

  function onNavClick(event: MouseEvent<HTMLElement>) {
    const link = (event.target as Element).closest('a[href^="#"]');
    const key = link?.getAttribute("href")?.slice(1);
    if (key && keys.includes(key)) select(key);
  }

  return (
    <div>
      <div onClick={onNavClick}>
        <TreeView data={withHashLinks(data)} activeHref={`#${active}`} orientation="horizontal" collapseBelow={false} aria-label={rest["aria-label"]} />
      </div>
      <div style={{ paddingTop: 12 }}>
        {keys.map((key) => (
          <div key={key} id={`panel-${key}`} hidden={active !== key}>
            {keepMounted || active === key ? panels[key] : null}
          </div>
        ))}
      </div>
    </div>
  );
}

