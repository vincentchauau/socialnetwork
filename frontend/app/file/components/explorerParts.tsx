"use client";

import { type ReactNode } from "react";

import { Icon } from "@sn/elements/Icon";
import { pickLanguage } from "@sn/lib/i18n";
import type { TreeNode } from "@sn/compounds/TreeView";

import { joinPath } from "../lib/paths";
import type { Entry } from "../lib/types";

export const ROOT = "/";

export type Row = Entry & { dir: string };

export const svg = (body: string) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: body }} />
);
export const ICON = {
  add: svg('<path d="M12 5v14M5 12h14"/>'),
  upload: svg('<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>'),
  rename: svg('<path d="M4 20h4L19 9l-4-4L4 16z"/>'),
  trash: svg('<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>'),
  cut: svg('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>'),
  copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
  paste: svg('<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4V3h6v1"/>'),
  details: svg('<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>'),
  columns: svg('<path d="M4 6h4v12H4zM10 6h4v12h-4zM16 6h4v12h-4z"/>'),
  small: svg('<rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/>'),
  large: svg('<rect x="4" y="4" width="16" height="16" rx="2"/>'),
  back: svg('<path d="M19 12H5M11 6l-6 6 6 6"/>'),
  forward: svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  refresh: svg('<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>'),
  up: svg('<path d="M12 19V5M6 11l6-6 6 6"/>'),
};
export const text = (vi: string, en: string) => pickLanguage(`${vi} / ${en}`);

/** The icon of an entry as Windows draws it: a yellow folder, or a white page with a fold (the same for every kind of file). */
export function iconOf(entry: Entry, size: number): ReactNode {
  if (entry.type === "folder") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 5.5A1.5 1.5 0 0 1 3.5 4h5.2l2 2.2h9.8A1.5 1.5 0 0 1 22 7.7V18a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 18z" fill="#e8b84a" />
        <path d="M2 9.5h20V18a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 18z" fill="#f9d978" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 3h8.5L19 7.5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" fill="var(--solid-0)" stroke="var(--line)" strokeWidth="1" />
      <path d="M14.5 3v4.5H19" fill="var(--solid-1)" stroke="var(--line)" strokeWidth="1" />
    </svg>
  );
}

/** The kind of an entry by its name: folder, image, audio, video or other. */
export function kindOf(entry: Entry): "folder" | "image" | "audio" | "video" | "file" {
  if (entry.type === "folder") return "folder";
  const ext = entry.name.split(".").pop()?.toLowerCase() ?? "";
  if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "image";
  if (["mp3", "wav", "ogg", "m4a"].includes(ext)) return "audio";
  if (["mp4", "webm", "mov"].includes(ext)) return "video";
  return "file";
}

/** The type column of the details view. */
export function typeOf(entry: Entry): string {
  if (entry.type === "folder") return text("Thư mục", "Folder");
  const ext = entry.name.includes(".") ? entry.name.split(".").pop()?.toUpperCase() : "";
  return ext ? `${ext} ${text("tệp", "file")}` : text("Tệp", "File");
}

/** The modified time of an entry (the server counts seconds). */
export function timeOf(modifiedAt: string): string {
  const seconds = Number(modifiedAt) || 0;
  return seconds > 0 ? new Date(seconds * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "";
}

/** The folder above a virtual path ("/" for a top-level item). */
export const parentOf = (path: string): string => "/" + path.split("/").filter(Boolean).slice(0, -1).join("/");

/** The key of a row: its full virtual path. */
export const keyOf = (row: Row): string => joinPath(row.dir, row.name);

/** The folder tree from the root: the folders the person has opened, as nodes. */
export function treeOf(known: ReadonlyMap<string, string[]>, rootLabel: string): TreeNode[] {
  const node = (folder: string, label: string): TreeNode => ({
    key: folder,
    label,
    expandable: !known.has(folder) || (known.get(folder)?.length ?? 0) > 0,
    children: (known.get(folder) ?? []).map((name) => node(joinPath(folder, name), name)),
  });
  return [{ key: ROOT, label: rootLabel, expandable: true, children: (known.get(ROOT) ?? []).map((name) => node(joinPath(ROOT, name), name)) }];
}

/** The folders on the way to `path`, root included: they are open in the tree so the current folder is visible. */
export function openOnThe(path: string): Set<string> {
  const keys = new Set<string>([ROOT]);
  const parts = path.split("/").filter(Boolean);
  parts.forEach((_, index) => keys.add("/" + parts.slice(0, index + 1).join("/")));
  return keys;
}

/** A modal panel over the page; a click outside closes it. */
export function Dialog({ label, wide = false, onClose, children }: { label: string; wide?: boolean; onClose: () => void; children: ReactNode }) {
  return (
    <div role="dialog" aria-label={label} onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 90, display: "flex", alignItems: "center", justifyContent: "center", background: "color-mix(in srgb, var(--line) 25%, transparent)" }}>
      <div onClick={(event) => event.stopPropagation()} style={{ width: wide ? "min(760px, 92vw)" : "min(440px, 92vw)", maxHeight: "86vh", overflow: "auto", padding: 18, borderRadius: 10, background: "var(--solid-0, #ffffff)", color: "inherit", fontSize: 13 }}>
        {children}
      </div>
    </div>
  );
}
