"use client";

import { type MouseEvent, type ReactNode, useEffect, useId, useState } from "react";

import Button from "../elements/Button";
import Icon from "../elements/Icon";
import { BG, BORDER, SURFACE } from "../lib/theme";
import { isActivePath } from "../lib/nav";

export interface TreeNode {
  key: string;
  label: string;
  /** With an href the node is a real link; without one it is a button that calls `onSelect`. */
  href?: string;
  /** Name of an `Icon`; shown in the vertical layout only. */
  icon?: string;
  /** The link is current only on its own page, not on the pages below it (a section's start page next to its sub-pages). */
  exact?: boolean;
  children?: TreeNode[];
  /** A node that may have children that are not known yet (it has the arrow to open it, and `onExpand` is told when it opens). */
  expandable?: boolean;
}

export interface TreeViewProps {
  data: readonly TreeNode[];
  /** Called with the key of a node that has no `href`. */
  onSelect?: (key: string) => void;
  /**
   * "vertical" (default) is an indented tree whose parents expand and collapse. "horizontal" is a bar: the
   * top level in a row, the children of a parent in a drop-down.
   */
  orientation?: "vertical" | "horizontal";
  /**
   * Horizontal only: below this window width (px) the bar turns vertical. The entries go into a column under
   * the bar and are shown by a menu button; a parent's children open inline instead of in a drop-down.
   * `false` keeps the bar horizontal at every width. Default 640.
   */
  collapseBelow?: number | false;
  /**
   * Path of the current page (with a #hash when links differ by hash). Omit it to read `window.location`
   * after mount: the pathname, which includes an app's basePath, and the hash.
   */
  activeHref?: string;
  /**
   * After mount, follow `window.location` (and its hash changes) instead of keeping `activeHref`. `activeHref`
   * is still what the server renders, so the first paint is right.
   */
  followLocation?: boolean;
  /** Vertical only: the parents that are open (the others are closed until pressed); left out, a parent is open when it holds the current link. */
  expandedKeys?: ReadonlySet<string>;
  /** Vertical only: told the key of a node that is opened (to load its children). */
  onExpand?: (key: string) => void;
  /** Vertical only: a node without the arrow keeps the room of one, so the names of all the nodes of a level start at the same place. */
  alignLeaves?: boolean;
  /** The node that is the current one (marked `aria-current`) when the nodes are not links. */
  currentKey?: string;
  /** Names the <nav> landmark; without it the tree is not wrapped in <nav>. */
  "aria-label"?: string;
  /** Horizontal only: before the entries (a logo, say). */
  brand?: ReactNode;
  /** Horizontal only: after the entries, pushed to the right (a ThemePicker, say). */
  trailing?: ReactNode;
  toggleLabel?: string;
  /** Accessible name of the menu button shown when the bar has turned vertical. */
  menuLabel?: string;
}

const DEFAULT_COLLAPSE_BELOW = 640;

// Self-contained, so an app needs no CSS of its own for it. The narrow-window rules sit in a media query so the
// switch needs no JavaScript and is right on the first paint, also in server-rendered layouts. The rules are global, so
// a page with several trees (a bar and a tab bar) shares them: the narrow-window rules are tied to `.sn-tree-collapsible`,
// the class of the bars that collapse, so another tree's plain rules (which come later in the page) cannot undo them.
function treeCss(collapseBelow: number | false): string {
  const base = `
.sn-tree-entry { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: none; border-radius: 8px; background: transparent; color: inherit; font: inherit; text-decoration: none; cursor: pointer; }
.sn-tree-entry:hover { background: color-mix(in srgb, ${SURFACE} 55%, transparent); }
.sn-tree-entry[aria-current="page"], .sn-tree-entry[aria-current="true"], .sn-tree-entry[data-active] { font-weight: 700; background: ${SURFACE} !important; }
.sn-tree-toggle { width: 28px; padding: 0 4px; border: none; background: transparent; color: inherit; cursor: pointer; }
.sn-tree-menu { display: none; }
.sn-tree-menu, .sn-tree-toggle { flex: none; }
.sn-tree-entry::after, .sn-tree-toggle::after, .sn-tree-menu::after { content: none; }
.sn-tree-list { display: flex; flex-wrap: wrap; gap: 4px; flex: 1; }
.sn-tree-dropdown { position: absolute; left: 0; top: 100%; z-index: 40; min-width: 180px; padding: 4px; background: ${BG}; border: 1px solid ${BORDER}; border-radius: 8px;}; }
`;
  if (collapseBelow === false) return base;
  return `${base}@media (max-width: ${collapseBelow - 1}px) {
  .sn-tree-collapsible .sn-tree-menu { display: inline-flex; }
  .sn-tree-collapsible.sn-tree-bar[data-menu-open] { position: fixed; inset: 0; z-index: 100; overflow-y: auto; align-content: flex-start; background: ${BG}; }
  .sn-tree-collapsible .sn-tree-list { display: none; flex-direction: column; flex: 1 1 100%; order: 3; gap: 2px; }
  .sn-tree-collapsible .sn-tree-list[data-open] { display: flex; }
  .sn-tree-collapsible .sn-tree-list > li { width: 100%; }
  .sn-tree-collapsible .sn-tree-list .sn-tree-entry { width: 100%; box-sizing: border-box; padding: 12px 16px; }
  .sn-tree-collapsible .sn-tree-trailing { display: none; flex: 1 1 100%; order: 4; width: 100%; box-sizing: border-box; padding: 0 12px; }
  .sn-tree-collapsible .sn-tree-trailing[data-open] { display: flex; }
  .sn-tree-collapsible .sn-tree-dropdown { position: static; min-width: 0; padding: 0 0 0 16px; background: transparent; border: none; }
}
`;
}

const LIST: React.CSSProperties = { listStyle: "none", margin: 0, padding: 0 };

export function TreeView(props: TreeViewProps) {
  const { data, onSelect, orientation = "vertical", activeHref, followLocation = false, brand, trailing, toggleLabel = "Toggle" } = props;
  const { collapseBelow = DEFAULT_COLLAPSE_BELOW, menuLabel = "Menu" } = props;
  const [browserPath, setBrowserPath] = useState<string>();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const listId = useId();

  // Read where the browser is once mounted; keep reading while the hash or the history changes if asked to follow.
  const watchLocation = activeHref === undefined || followLocation;
  useEffect(() => {
    if (!watchLocation) return;
    const read = () => setBrowserPath(window.location.pathname + window.location.hash);
    read();
    window.addEventListener("hashchange", read);
    window.addEventListener("popstate", read);
    return () => {
      window.removeEventListener("hashchange", read);
      window.removeEventListener("popstate", read);
    };
  }, [watchLocation]);

  // A drop-down and the narrow-window menu close on Escape; a drop-down also on a press outside it.
  const anythingOpen = openKey !== null || menuOpen;
  useEffect(() => {
    if (!anythingOpen) return;
    function onPointerDown(event: globalThis.MouseEvent) {
      if (!(event.target as Element).closest("li[data-open]")) setOpenKey(null);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpenKey(null);
      setMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [anythingOpen]);

  const current = followLocation && browserPath !== undefined ? browserPath : (activeHref ?? browserPath);
  const isActive = (node: TreeNode) => node.href !== undefined && isActivePath(node.href, current, node.exact);
  const containsActive = (node: TreeNode): boolean => isActive(node) || (node.children ?? []).some(containsActive);

  function entry(node: TreeNode, withIcon: boolean) {
    const content = (
      <>
        {withIcon && node.icon && <Icon name={node.icon} size={20} />}
        {node.label}
      </>
    );
    if (node.href !== undefined) {
      return (
        <a className="sn-tree-entry" href={node.href} aria-current={isActive(node) ? "page" : undefined}>
          {content}
        </a>
      );
    }
    return (
      <Button type="button" variant="ghost" className="sn-tree-entry" aria-current={props.currentKey === node.key ? "true" : undefined} onClick={() => onSelect?.(node.key)}>
        {content}
      </Button>
    );
  }

  function renderVertical(node: TreeNode): ReactNode {
    const children = node.children ?? [];
    const isOpen = expanded[node.key] ?? (props.expandedKeys ? props.expandedKeys.has(node.key) : containsActive(node));
    const canOpen = children.length > 0 || node.expandable === true;
    return (
      <li key={node.key} style={{ listStyle: "none" }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          {canOpen && (
            <Button
              type="button"
              variant="ghost"
              className="sn-tree-toggle"
              aria-label={`${toggleLabel} ${node.label}`}
              aria-expanded={isOpen}
              onClick={() => {
                setExpanded((state) => ({ ...state, [node.key]: !isOpen }));
                if (!isOpen) props.onExpand?.(node.key);
              }}
            >
              {isOpen ? "▾" : "▸"}
            </Button>
          )}
          {!canOpen && props.alignLeaves && <span className="sn-tree-toggle" aria-hidden="true" />}
          {entry(node, true)}
        </div>
        {children.length > 0 && isOpen && <ul style={{ ...LIST, paddingLeft: 16 }}>{children.map(renderVertical)}</ul>}
      </li>
    );
  }

  const Root = props["aria-label"] ? "nav" : "div";
  const css = treeCss(orientation === "horizontal" ? collapseBelow : false);

  if (orientation === "vertical") {
    return (
      <Root aria-label={props["aria-label"]}>
        <style>{css}</style>
        <ul style={LIST}>{data.map(renderVertical)}</ul>
      </Root>
    );
  }

  // Picking an entry closes the drop-down and the narrow-window menu; a parent's own button only opens its children.
  function onListClick(event: MouseEvent<HTMLElement>) {
    const picked = (event.target as Element).closest(".sn-tree-entry");
    if (!picked || picked.hasAttribute("data-parent")) return;
    setOpenKey(null);
    setMenuOpen(false);
  }

  return (
    <Root
      aria-label={props["aria-label"]}
      className={collapseBelow === false ? "sn-tree-bar" : "sn-tree-bar sn-tree-collapsible"}
      data-menu-open={menuOpen || undefined}
      style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "8px 12px", borderBottom: `1px solid ${BORDER}` }}
    >
      <style>{css}</style>
      {brand}
      {collapseBelow !== false && (
        <Button
          type="button"
          variant="ghost"
          className="sn-tree-menu"
          aria-label={menuLabel}
          aria-expanded={menuOpen}
          aria-controls={listId}
          onClick={() => setMenuOpen((open) => !open)}
          style={{ padding: 8, borderRadius: 8, background: SURFACE, alignItems: "center", justifyContent: "center" }}
        >
          <Icon name={menuOpen ? "close" : "menu"} size={22} />
        </Button>
      )}
      <ul id={listId} className="sn-tree-list" data-open={menuOpen || undefined} style={LIST} onClick={onListClick}>
        {data.map((node) => {
          const children = node.children ?? [];
          if (children.length === 0) return <li key={node.key}>{entry(node, false)}</li>;
          const isOpen = openKey === node.key;
          return (
            <li key={node.key} style={{ position: "relative" }} data-open={isOpen || undefined}>
              <Button
                type="button"
                variant="ghost"
                className="sn-tree-entry"
                style={containsActive(node) ? { background: SURFACE } : undefined}
                data-parent=""
                aria-expanded={isOpen}
                aria-haspopup="true"
                data-active={containsActive(node) || undefined}
                onClick={() => setOpenKey(isOpen ? null : node.key)}
              >
                {node.label} ▾
              </Button>
              {isOpen && (
                <div className="sn-tree-dropdown">
                  <ul style={LIST}>{children.map(renderVertical)}</ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {trailing !== undefined && <div className="sn-tree-trailing" data-open={menuOpen || undefined}>{trailing}</div>}
    </Root>
  );
}

export default TreeView;
