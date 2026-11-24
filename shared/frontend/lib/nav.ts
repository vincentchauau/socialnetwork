import type { TreeNode } from "../compounds/TreeView";
import { MENU } from "./apps";

function split(url: string): { path: string; hash: string } {
  const at = url.indexOf("#");
  const path = at < 0 ? url : url.slice(0, at);
  return { path: path.length > 1 ? path.replace(/\/+$/, "") : path, hash: at < 0 ? "" : url.slice(at) };
}

/**
 * Whether the link `href` is the one for the page `current` (a path, optionally with a #hash).
 * The home link matches only itself; any other link also matches the pages below it. A link with a hash
 * (`/work#file`) matches only while that hash is current, so two views of one page are told apart. With `exact` a link
 * does not match the pages below it either.
 */
export function isActivePath(href: string, current: string | undefined, exact = false): boolean {
  if (current === undefined) return false;
  const target = split(href);
  const here = split(current);
  const samePath =
    target.path === "/" || exact ? here.path === target.path : here.path === target.path || here.path.startsWith(`${target.path}/`);
  return samePath && (target.hash === "" || target.hash === here.hash);
}

/** The entries of the main navigation, in the order of MENU (generated). No app has a place of its own beyond its entry; the chat of each app is the dock under its page. */
export const NAV_NODES: readonly TreeNode[] = MENU.map((entry) => ({ key: entry.href, label: entry.name, href: entry.href, icon: "apps" }));

