"use client";

import { type DragEvent, type MouseEvent as ReactMouseEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import ContextMenu, { type ContextMenuItem } from "@sn/compounds/ContextMenu";
import { GridView } from "@sn/compounds/GalleryView";
import TreeView, { type TreeNode } from "@sn/compounds/TreeView";
import Button from "@sn/elements/Button";
import { Icon } from "@sn/elements/Icon";
import TextBox from "@sn/elements/TextBox";
import { pickLanguage } from "@sn/lib/i18n";
import { LINE_SOFT } from "@sn/lib/theme";
import { useSession } from "@sn/lib/useSession";

import { copyEntry, createFolder, deleteEntry, listFiles, moveEntry, renameEntry, searchFolder, uploadFile } from "../lib/api";
import { type Area, breadcrumbs, downloadUrl, formatBytes, joinPath, nameProblem } from "../lib/paths";
import type { Entry, Listing } from "../lib/types";
import ShareSection from "./ShareSection";
import TrashPanel from "./TrashPanel";
import VersionsSection from "./VersionsSection";

const ROOT = "/";
// The one border colour of the Explorer: the shared light line-colour of the theme (no new variable).
const LINE = `1px solid ${LINE_SOFT}`;
const HOVER = "color-mix(in srgb, var(--line) 16%, transparent)";

type SortKey = "name" | "date" | "type" | "size";
type ColumnKey = SortKey;
type ViewMode = "details" | "list" | "small" | "large";
/** A row of the folder or of a search result: the entry and the folder it sits in. */
type Row = Entry & { dir: string };
type Modal = { kind: "trash" } | { kind: "versions" | "share" | "preview" | "properties"; row: Row } | null;

const CSS = `
.fx-root { font-size: 13px; }
.fx-tool { display: inline-flex; align-items: center; gap: 6px; padding: 5px 9px; border: 0; border-radius: 6px; background: transparent; color: inherit; font: inherit; font-size: 13px; white-space: nowrap; cursor: pointer; }
.fx-tool:hover:not(:disabled) { background: color-mix(in srgb, var(--line) 10%, transparent); }
.fx-tool:disabled { opacity: 0.4; cursor: default; }
.fx-tool.fx-danger:not(:disabled) { color: var(--line); font-weight: 600; text-decoration: underline; }
.fx-nav { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: 0; border-radius: 6px; background: transparent; color: inherit; cursor: pointer; }
.fx-nav:hover:not(:disabled) { background: color-mix(in srgb, var(--line) 10%, transparent); }
.fx-nav:disabled { opacity: 0.35; cursor: default; }
.fx-crumb { border: 0; border-radius: 4px; background: transparent; color: inherit; font: inherit; padding: 2px 5px; cursor: pointer; white-space: nowrap; }
.fx-crumb:hover { background: color-mix(in srgb, var(--line) 10%, transparent); }
.fx-row:hover, .fx-tile:hover { background: color-mix(in srgb, var(--line) 8%, transparent) !important; }
.fx-tool:focus-visible, .fx-nav:focus-visible, .fx-crumb:focus-visible, .fx-tile:focus-visible { outline: 2px solid color-mix(in srgb, var(--line) 50%, transparent); outline-offset: 1px; }
.fx-tool, .fx-nav, .fx-crumb { border: 0 !important; }
.fx-tool:disabled, .fx-nav:disabled { border: 0 !important; }
.fx-root .sn-tree-toggle { width: 20px; min-width: 20px; height: 22px; padding: 0; border: 0; display: inline-flex; align-items: center; justify-content: center; flex: none; font-size: 14px; }
.fx-root ul ul { padding-left: 14px !important; }
.fx-root .sn-tree-entry { min-width: max-content; }
.fx-root .sn-tree-toggle { color: inherit !important; opacity: 1 !important; background: transparent !important; }
.fx-root .sn-tree-entry::before { content: ""; flex: none; width: 16px; height: 16px; background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M2 5.5A1.5 1.5 0 0 1 3.5 4h5.2l2 2.2h9.8A1.5 1.5 0 0 1 22 7.7V18a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 18z' fill='%23e8b84a'/%3E%3Cpath d='M2 9.5h20V18a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 2 18z' fill='%23f9d978'/%3E%3C/svg%3E") center / contain no-repeat; }
.fx-root .sn-tree-entry { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; padding: 3px 6px; border: 0; border-radius: 4px; font-size: 13px; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fx-root .sn-tree-entry:hover { background: color-mix(in srgb, var(--line) 8%, transparent); }
.fx-root .sn-tree-entry[aria-current="true"] { background: color-mix(in srgb, var(--line) 16%, transparent); font-weight: 600; }
`;

const svg = (body: string) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: body }} />
);
const ICON = {
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
const text = (vi: string, en: string) => pickLanguage(`${vi} / ${en}`);

/** The icon of an entry as Windows draws it: a yellow folder, or a white page with a fold (the same for every kind of file). */
function iconOf(entry: Entry, size: number): ReactNode {
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
function kindOf(entry: Entry): "folder" | "image" | "audio" | "video" | "file" {
  if (entry.type === "folder") return "folder";
  const ext = entry.name.split(".").pop()?.toLowerCase() ?? "";
  if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "image";
  if (["mp3", "wav", "ogg", "m4a"].includes(ext)) return "audio";
  if (["mp4", "webm", "mov"].includes(ext)) return "video";
  return "file";
}

/** The type column of the details view. */
function typeOf(entry: Entry): string {
  if (entry.type === "folder") return text("Thư mục", "Folder");
  const ext = entry.name.includes(".") ? entry.name.split(".").pop()?.toUpperCase() : "";
  return ext ? `${ext} ${text("tệp", "file")}` : text("Tệp", "File");
}

/** The modified time of an entry (the server counts seconds). */
function timeOf(modifiedAt: string): string {
  const seconds = Number(modifiedAt) || 0;
  return seconds > 0 ? new Date(seconds * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }) : "";
}

/** The folder above a virtual path ("/" for a top-level item). */
const parentOf = (path: string): string => "/" + path.split("/").filter(Boolean).slice(0, -1).join("/");

/** The key of a row: its full virtual path. */
const keyOf = (row: Row): string => joinPath(row.dir, row.name);

/** The folder tree from the root: the folders the person has opened, as nodes. */
function treeOf(known: ReadonlyMap<string, string[]>, rootLabel: string): TreeNode[] {
  const node = (folder: string, label: string): TreeNode => ({
    key: folder,
    label,
    expandable: !known.has(folder) || (known.get(folder)?.length ?? 0) > 0,
    children: (known.get(folder) ?? []).map((name) => node(joinPath(folder, name), name)),
  });
  return [{ key: ROOT, label: rootLabel, expandable: true, children: (known.get(ROOT) ?? []).map((name) => node(joinPath(ROOT, name), name)) }];
}

/** The folders on the way to `path`, root included: they are open in the tree so the current folder is visible. */
function openOnThe(path: string): Set<string> {
  const keys = new Set<string>([ROOT]);
  const parts = path.split("/").filter(Boolean);
  parts.forEach((_, index) => keys.add("/" + parts.slice(0, index + 1).join("/")));
  return keys;
}

/** A modal panel over the page; a click outside closes it. */
function Dialog({ label, wide = false, onClose, children }: { label: string; wide?: boolean; onClose: () => void; children: ReactNode }) {
  return (
    <div role="dialog" aria-label={label} onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 90, display: "flex", alignItems: "center", justifyContent: "center", background: "color-mix(in srgb, var(--line) 25%, transparent)" }}>
      <div onClick={(event) => event.stopPropagation()} style={{ width: wide ? "min(760px, 92vw)" : "min(440px, 92vw)", maxHeight: "86vh", overflow: "auto", padding: 18, borderRadius: 10, background: "var(--solid-0, #ffffff)", color: "inherit", fontSize: 13 }}>
        {children}
      </div>
    </div>
  );
}

/** The files as Windows Explorer shows them: a folder tree, toolbar, address bar, search, views, cut/copy/paste, selection by drag, preview, trash, versions and sharing. */
export default function Explorer() {
  // The root is the person's own folder; an admin works in the data folder of the backend (where every app keeps its files).
  const session = useSession();
  const area: Area = session.status === "signed-in" && session.user.group === "admin" ? "data" : "mine";
  const ready = session.status !== "loading";

  const [path, setPath] = useState(ROOT);
  const [history, setHistory] = useState<string[]>([]);
  const [forward, setForward] = useState<string[]>([]);
  const [listing, setListing] = useState<Listing | null>(null);
  const [known, setKnown] = useState<ReadonlyMap<string, string[]>>(new Map());
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [clip, setClip] = useState<{ mode: "copy" | "cut"; keys: string[] } | null>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; row: Row | null } | null>(null);
  const [naming, setNaming] = useState<{ kind: "folder" | "rename"; value: string; target?: string } | null>(null);
  const [modal, setModal] = useState<Modal>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Row[] | null>(null);
  const [view, setView] = useState<ViewMode>("details");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "name", dir: 1 });
  const [widths, setWidths] = useState<Record<ColumnKey, number>>({ name: 320, date: 170, type: 130, size: 100 });
  const [editing, setEditing] = useState<string | null>(null);
  const [band, setBand] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const upload = useRef<HTMLInputElement>(null);
  const anchor = useRef<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const dragged = useRef(false);

  // Only the newest request may change the screen: an older answer (for another area) arriving late is dropped.
  const latest = useRef(0);
  const load = useCallback(async (folder: string) => {
    const request = ++latest.current;
    setError("");
    try {
      const data = await listFiles(folder, area);
      if (request !== latest.current) return;
      setListing(data);
      setSelected(new Set());
      setKnown((current) => {
        const next = new Map(current);
        next.set(folder, data.entries.filter((entry) => entry.type === "folder").map((entry) => entry.name));
        return next;
      });
    } catch (failure) {
      if (request !== latest.current) return;
      setError(failure instanceof Error ? failure.message : text("Không mở được thư mục", "The folder could not be opened"));
    }
  }, [area]);

  useEffect(() => {
    if (!ready) return;
    setPath(ROOT);
    setHistory([]);
    setForward([]);
    void load(ROOT);
  }, [load, ready]);

  useEffect(() => {
    if (!ready) return;
    void load(path);
  }, [path, load, ready]);

  // Search goes through the folder and everything below it, after a short pause in typing.
  const needle = query.trim();
  useEffect(() => {
    if (!ready || needle === "") {
      setFound(null);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      searchFolder(path, needle, area)
        .then((data) => {
          if (live) setFound(data.entries.map((hit) => ({ ...hit, dir: parentOf(hit.path) })));
        })
        .catch((failure: unknown) => {
          if (live) setError(failure instanceof Error ? failure.message : text("Không tìm được", "The search failed"));
        });
    }, 300);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [needle, path, area, ready]);

  const entries = useMemo(() => listing?.entries ?? [], [listing]);
  const rows = useMemo<Row[]>(() => found ?? entries.map((entry) => ({ ...entry, dir: path })), [found, entries, path]);
  const shown = useMemo(() => {
    const valueOf = (row: Row): number | string => {
      if (sort.key === "date") return Number(row.modifiedAt) || 0;
      if (sort.key === "size") return row.size;
      if (sort.key === "type") return typeOf(row);
      return row.name.toLocaleLowerCase();
    };
    return [...rows].sort((a, b) => {
      if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
      const x = valueOf(a);
      const y = valueOf(b);
      const order = x < y ? -1 : x > y ? 1 : 0;
      return order * sort.dir || a.name.localeCompare(b.name);
    });
  }, [rows, sort]);
  const selectedRows = useMemo(() => shown.filter((row) => selected.has(keyOf(row))), [shown, selected]);
  const crumbs = useMemo(() => breadcrumbs(path), [path]);
  // The root is named "data" everywhere (tree and address bar), for every role.
  const rootLabel = "data";
  const tree = useMemo<TreeNode[]>(() => treeOf(known, rootLabel), [known, rootLabel]);
  const expandedKeys = useMemo(() => openOnThe(path), [path]);

  const run = async (action: () => Promise<unknown>, failed: string) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await load(path);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : failed);
    } finally {
      setBusy(false);
    }
  };

  const navigate = (next: string) => {
    setQuery("");
    if (next === path) return;
    setHistory((current) => [...current, path]);
    setForward([]);
    setPath(next);
  };

  const goForward = () => {
    const next = forward[forward.length - 1];
    if (next === undefined) return;
    setForward(forward.slice(0, -1));
    setHistory((current) => [...current, path]);
    setQuery("");
    setPath(next);
  };

  const goBack = () => {
    const last = history[history.length - 1];
    if (last === undefined) return;
    setHistory(history.slice(0, -1));
    setForward((current) => [...current, path]);
    setQuery("");
    setPath(last);
  };

  const typedAddress = (value: string) => {
    const clean = "/" + value.split("/").filter(Boolean).join("/");
    setEditing(null);
    navigate(clean === "/" ? ROOT : clean);
  };

  const open = (row: Row) => {
    const key = keyOf(row);
    if (row.type === "folder") navigate(key);
    else if (kindOf(row) === "image" || kindOf(row) === "video" || kindOf(row) === "audio") setModal({ kind: "preview", row });
    else window.open(downloadUrl(key, area), "_blank");
  };

  const onRowClick = (row: Row, event: ReactMouseEvent) => {
    const key = keyOf(row);
    if (event.shiftKey && anchor.current) {
      const from = shown.findIndex((item) => keyOf(item) === anchor.current);
      const to = shown.findIndex((item) => keyOf(item) === key);
      if (from >= 0 && to >= 0) {
        const [low, high] = from < to ? [from, to] : [to, from];
        setSelected(new Set(shown.slice(low, high + 1).map(keyOf)));
        return;
      }
    }
    anchor.current = key;
    setSelected((current) => {
      if (event.ctrlKey || event.metaKey) {
        const next = new Set(current);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      }
      return new Set([key]);
    });
  };

  // Drag across empty space to select a block of items, as in Windows.
  const startBand = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (event.button !== 0 || (event.target as HTMLElement).closest("[data-key]")) return;
    const start = { x: event.clientX, y: event.clientY };
    const base = event.ctrlKey || event.metaKey ? new Set(selected) : new Set<string>();
    dragged.current = false;
    const move = (moved: MouseEvent) => {
      if (!dragged.current && Math.abs(moved.clientX - start.x) + Math.abs(moved.clientY - start.y) < 4) return;
      dragged.current = true;
      const box = {
        x0: Math.min(start.x, moved.clientX),
        y0: Math.min(start.y, moved.clientY),
        x1: Math.max(start.x, moved.clientX),
        y1: Math.max(start.y, moved.clientY),
      };
      setBand(box);
      const next = new Set(base);
      scroller.current?.querySelectorAll<HTMLElement>("[data-key]").forEach((node) => {
        const rect = node.getBoundingClientRect();
        if (rect.right >= box.x0 && rect.left <= box.x1 && rect.bottom >= box.y0 && rect.top <= box.y1 && node.dataset.key) next.add(node.dataset.key);
      });
      setSelected(next);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      setBand(null);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  // Columns: drag the right edge of a heading to change the width.
  const startResize = (column: ColumnKey) => (event: ReactMouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = widths[column];
    const move = (moved: MouseEvent) => setWidths((current) => ({ ...current, [column]: Math.max(60, startWidth + moved.clientX - startX) }));
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const sortBy = (key: SortKey) => setSort((current) => ({ key, dir: current.key === key ? (current.dir === 1 ? -1 : 1) : 1 }));

  const commitName = () => {
    if (!naming) return;
    const problem = nameProblem(naming.value);
    if (problem) return setError(problem);
    const current = naming;
    setNaming(null);
    if (current.kind === "folder") void run(() => createFolder(path, current.value, area), text("Không tạo được thư mục", "The folder could not be made"));
    else if (current.target) void run(() => renameEntry(current.target as string, current.value, area), text("Không đổi được tên", "It could not be renamed"));
  };

  const removeKeys = (keys: string[]) => {
    if (keys.length === 0) return;
    if (!window.confirm(text(`Xóa ${keys.length} mục?`, `Delete ${keys.length} item(s)?`))) return;
    void run(async () => {
      for (const key of keys) await deleteEntry(key, area);
    }, text("Không xóa được", "It could not be deleted"));
  };

  const setClipboard = (mode: "copy" | "cut", keys: string[]) => setClip({ mode, keys });

  const paste = () => {
    if (!clip) return;
    const { mode, keys } = clip;
    // A cut item already in this folder has nothing to move.
    const work = keys.filter((key) => !(mode === "cut" && parentOf(key) === path));
    if (mode === "cut") setClip(null);
    if (work.length === 0) return;
    void run(async () => {
      for (const key of work) {
        if (mode === "cut") await moveEntry(key, path, area);
        else await copyEntry(key, path, area);
      }
    }, text("Không dán được", "It could not be pasted"));
  };

  const onFiles = (files: FileList | null) => {
    const chosen = Array.from(files ?? []);
    if (chosen.length === 0) return;
    void run(async () => {
      for (const file of chosen) await uploadFile(path, file, area);
    }, text("Không tải lên được", "It could not be uploaded"));
  };

  const dragStart = (row: Row) => (event: DragEvent) => {
    event.dataTransfer.setData("text/plain", keyOf(row));
    event.dataTransfer.effectAllowed = "copyMove";
  };

  const dropOn = (folder: string) => (event: DragEvent) => {
    event.preventDefault();
    setDropTarget(null);
    const source = event.dataTransfer.getData("text/plain");
    if (!source || source === folder || folder.startsWith(`${source}/`) || parentOf(source) === folder) return;
    void run(() => moveEntry(source, folder, area), text("Không di chuyển được", "It could not be moved"));
  };

  const openMenu = (event: ReactMouseEvent, row: Row | null) => {
    event.preventDefault();
    event.stopPropagation();
    if (row && !selected.has(keyOf(row))) setSelected(new Set([keyOf(row)]));
    setMenu({ x: event.clientX, y: event.clientY, row });
  };

  const menuItems = (row: Row | null): ContextMenuItem[] => {
    const items: ContextMenuItem[] = [];
    if (row) {
      const key = keyOf(row);
      const targets = selected.has(key) ? [...selected] : [key];
      const previewable = ["image", "video", "audio"].includes(kindOf(row));
      items.push({ key: "open", label: row.type === "folder" ? text("Mở", "Open") : previewable ? text("Xem trước", "Preview") : text("Tải xuống", "Download"), onSelect: () => open(row) });
      items.push({ key: "cut", label: text("Cắt", "Cut"), onSelect: () => setClipboard("cut", targets) });
      items.push({ key: "copy", label: text("Sao chép", "Copy"), onSelect: () => setClipboard("copy", targets) });
      items.push({ key: "rename", label: text("Đổi tên", "Rename"), onSelect: () => setNaming({ kind: "rename", value: row.name, target: key }) });
      items.push({ key: "delete", label: text("Xóa", "Delete"), danger: true, onSelect: () => removeKeys(targets) });
      items.push({ key: "share", label: text("Chia sẻ", "Share"), onSelect: () => setModal({ kind: "share", row }) });
      if (row.type === "file") items.push({ key: "versions", label: text("Phiên bản trước", "Previous versions"), onSelect: () => setModal({ kind: "versions", row }) });
      items.push({ key: "properties", label: text("Thuộc tính", "Properties"), onSelect: () => setModal({ kind: "properties", row }) });
      return items;
    }
    if (clip) items.push({ key: "paste", label: text("Dán", "Paste"), onSelect: paste });
    items.push({ key: "folder", label: text("Thư mục mới", "New folder"), onSelect: () => setNaming({ kind: "folder", value: "" }) });
    items.push({ key: "upload", label: text("Tải tệp lên", "Upload files"), onSelect: () => upload.current?.click() });
    items.push({ key: "trash", label: text("Thùng rác", "Recycle Bin"), onSelect: () => setModal({ kind: "trash" }) });
    items.push({ key: "refresh", label: text("Làm mới", "Refresh"), onSelect: () => void load(path) });
    return items;
  };

  const itemHandlers = (row: Row) => {
    const key = keyOf(row);
    const isFolder = row.type === "folder";
    return {
      "data-key": key,
      draggable: true,
      onDragStart: dragStart(row),
      onDragOver: isFolder ? (event: DragEvent) => { event.preventDefault(); setDropTarget(key); } : undefined,
      onDragLeave: () => setDropTarget(null),
      onDrop: isFolder ? dropOn(key) : undefined,
      onClick: (event: ReactMouseEvent) => { event.stopPropagation(); onRowClick(row, event); },
      onDoubleClick: () => open(row),
      onContextMenu: (event: ReactMouseEvent) => openMenu(event, row),
    };
  };

  const rowBackground = (isSelected: boolean, key: string) =>
    isSelected ? "color-mix(in srgb, var(--line) 14%, transparent)" : dropTarget === key ? "color-mix(in srgb, var(--line) 8%, transparent)" : "transparent";

  const tool = (label: string, icon: ReactNode, onClick: () => void, disabled = false, danger = false) => (
    <button type="button" className={`fx-tool${danger ? " fx-danger" : ""}`} style={{ border: "0", outline: "none" }} onClick={onClick} disabled={disabled || busy} title={label} aria-label={label}>
      {icon}
      <span>{label}</span>
    </button>
  );

  const sortMark = (key: SortKey) => (sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : "");
  const header = (column: ColumnKey, label: string, align: "left" | "right" = "left") => (
    <th
      style={{ position: "relative", padding: "6px 8px", fontWeight: 600, textAlign: align, border: 0, borderBottom: LINE, cursor: "pointer", userSelect: "none", overflow: "hidden", whiteSpace: "nowrap" }}
      aria-sort={sort.key === column ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
      onClick={() => sortBy(column)}
    >
      {label}
      {sortMark(column)}
      <span
        role="separator"
        aria-hidden="true"
        onMouseDown={startResize(column)}
        onClick={(event) => event.stopPropagation()}
        style={{ position: "absolute", top: 0, right: -3, bottom: 0, width: 6, cursor: "col-resize" }}
      />
    </th>
  );

  const tile = (row: Row, mode: Exclude<ViewMode, "details">) => {
    const key = keyOf(row);
    const isSelected = selected.has(key);
    const isImage = kindOf(row) === "image";
    const large = mode === "large";
    const inline = mode === "list";
    const thumb = isImage && large ? <img src={downloadUrl(key, area)} alt="" loading="lazy" style={{ width: 96, height: 72, objectFit: "cover", borderRadius: 4 }} /> : iconOf(row, large ? 56 : inline ? 16 : 32);
    return (
      <div
        className="fx-tile"
        role="button"
        tabIndex={0}
        aria-pressed={isSelected}
        title={found ? key : row.name}
        {...itemHandlers(row)}
        style={{
          display: "flex",
          flexDirection: inline ? "row" : "column",
          alignItems: "center",
          gap: inline ? 8 : 4,
          padding: inline ? "4px 8px" : 8,
          borderRadius: 6,
          cursor: "default",
          minWidth: 0,
          background: rowBackground(isSelected, key),
          border: "1px solid transparent",
        }}
      >
        <span aria-hidden="true" style={{ display: "inline-flex", flex: "none" }}>{thumb}</span>
        <span style={{ fontSize: 12, textAlign: inline ? "left" : "center", maxWidth: "100%", minWidth: 0, overflow: "hidden", textOverflow: inline ? "ellipsis" : undefined, whiteSpace: inline ? "nowrap" : undefined, display: inline ? "block" : "-webkit-box", WebkitLineClamp: inline ? undefined : 2, WebkitBoxOrient: "vertical", overflowWrap: "anywhere" }}>{row.name}</span>
      </div>
    );
  };

  const tileSize = (mode: Exclude<ViewMode, "details">) => (mode === "large" ? 150 : mode === "small" ? 120 : 220);

  const views = (
    <div
      ref={scroller}
      style={{ flex: 1, minHeight: 0, overflow: "auto", position: "relative" }}
      onMouseDown={startBand}
      onContextMenu={(event) => openMenu(event, null)}
      onClick={() => {
        if (dragged.current) {
          dragged.current = false;
          return;
        }
        setSelected(new Set());
      }}
      onDragOver={(event) => { event.preventDefault(); setDropTarget(path); }}
      onDrop={dropOn(path)}
    >
      {view === "details" ? (
        <table aria-label={text("Tệp và thư mục", "Files and folders")} style={{ width: "100%", tableLayout: "fixed", borderCollapse: "collapse", fontSize: 13 }}>
          <colgroup>
            <col style={{ width: widths.name }} />
            <col style={{ width: widths.date }} />
            <col style={{ width: widths.type }} />
            <col style={{ width: widths.size }} />
          </colgroup>
          <thead>
            <tr style={{ textAlign: "left" }}>
              {header("name", text("Tên", "Name"))}
              {header("date", text("Ngày sửa", "Date modified"))}
              {header("type", text("Loại", "Type"))}
              {header("size", text("Kích thước", "Size"), "right")}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => {
              const key = keyOf(row);
              const isSelected = selected.has(key);
              const cell = { padding: "5px 8px", border: 0, borderBottom: LINE, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } as const;
              return (
                <tr key={key} aria-selected={isSelected} className="fx-row" {...itemHandlers(row)} onDragLeave={() => setDropTarget(null)} style={{ cursor: "default", background: rowBackground(isSelected, key) }}>
                  <td title={found ? key : row.name} style={cell}>
                    <span aria-hidden="true" style={{ display: "inline-flex", verticalAlign: "middle", marginRight: 8 }}>{iconOf(row, 16)}</span>
                    {row.name}
                    {found ? <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>{row.dir}</span> : null}
                  </td>
                  <td style={{ ...cell, whiteSpace: "nowrap" }}>{timeOf(row.modifiedAt)}</td>
                  <td style={cell}>{typeOf(row)}</td>
                  <td style={{ ...cell, textAlign: "right" }}>{row.type === "file" ? formatBytes(row.size) : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <GridView
          label={text("Tệp và thư mục", "Files and folders")}
          items={shown}
          itemKey={keyOf}
          minColumnWidth={tileSize(view)}
          gap={6}
          empty={<p className="muted" style={{ margin: 0 }}>{found ? text("Không có kết quả.", "No results.") : text("Thư mục này đang trống.", "This folder is empty.")}</p>}
          renderItem={(row) => tile(row, view)}
        />
      )}
      {band ? (
        <div style={{ position: "fixed", left: band.x0, top: band.y0, width: band.x1 - band.x0, height: band.y1 - band.y0, border: "1px solid color-mix(in srgb, var(--line) 45%, transparent)", background: "color-mix(in srgb, var(--line) 8%, transparent)", pointerEvents: "none", zIndex: 50 }} />
      ) : null}
    </div>
  );

  // The view buttons carry their names: an icon alone was not clear enough which view it switches to.
  const modeButton = (mode: ViewMode, label: string) => (
    <button
      type="button"
      className="fx-tool"
      aria-label={label}
      aria-pressed={view === mode}
      title={label}
      onClick={() => setView(mode)}
      style={{ padding: "3px 8px", fontSize: 12, background: view === mode ? HOVER : "transparent" }}
    >
      {label}
    </button>
  );

  const main: ReactNode = (
    <div style={{ display: "flex", flexDirection: "column", minWidth: 0, height: "100%" }}>
      <div role="toolbar" aria-label={text("Công cụ", "Tools")} style={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center", paddingBottom: 6, borderBottom: LINE }}>
        {tool(text("Mới", "New"), ICON.add, () => setNaming({ kind: "folder", value: "" }))}
        {tool(text("Tải lên", "Upload"), ICON.upload, () => upload.current?.click())}
        {tool(text("Cắt", "Cut"), ICON.cut, () => setClipboard("cut", [...selected]), selectedRows.length === 0)}
        {tool(text("Sao chép", "Copy"), ICON.copy, () => setClipboard("copy", [...selected]), selectedRows.length === 0)}
        {tool(text("Dán", "Paste"), ICON.paste, paste, !clip)}
        {tool(text("Đổi tên", "Rename"), ICON.rename, () => selectedRows[0] && setNaming({ kind: "rename", value: selectedRows[0].name, target: keyOf(selectedRows[0]) }), selectedRows.length !== 1)}
        {tool(text("Xóa", "Delete"), ICON.trash, () => removeKeys([...selected]), selectedRows.length === 0, true)}
        <span style={{ flex: 1 }} />
        {tool(text("Thùng rác", "Recycle Bin"), ICON.trash, () => setModal({ kind: "trash" }))}
        {tool(text("Làm mới", "Refresh"), ICON.refresh, () => void load(path))}
        <input ref={upload} type="file" multiple style={{ display: "none" }} onChange={(event) => { onFiles(event.target.files); event.target.value = ""; }} />
      </div>

      <div style={{ display: "flex", gap: 6, alignItems: "center", padding: "8px 0" }}>
        <button type="button" className="fx-nav" style={{ width: 28, height: 28, minWidth: 28 }} aria-label={text("Quay lại", "Back")} title={text("Quay lại", "Back")} disabled={history.length === 0} onClick={goBack}>{ICON.back}</button>
        <button type="button" className="fx-nav" style={{ width: 28, height: 28, minWidth: 28 }} aria-label={text("Đi tiếp", "Forward")} title={text("Đi tiếp", "Forward")} disabled={forward.length === 0} onClick={goForward}>{ICON.forward}</button>
        <button type="button" className="fx-nav" style={{ width: 28, height: 28, minWidth: 28 }} aria-label={text("Lên", "Up")} title={text("Lên", "Up")} disabled={path === ROOT} onClick={() => navigate(parentOf(path))}>{ICON.up}</button>
        {editing !== null ? (
          <input
            aria-label={text("Đường dẫn", "Address")}
            autoFocus
            value={editing}
            onChange={(event) => setEditing(event.target.value)}
            onBlur={() => setEditing(null)}
            onKeyDown={(event) => { if (event.key === "Enter") typedAddress(editing); if (event.key === "Escape") setEditing(null); }}
            style={{ flex: 1, minWidth: 0, height: 30, boxSizing: "border-box", padding: "0 8px", borderRadius: 6, fontSize: 13, background: "transparent", color: "inherit", border: LINE }}
          />
        ) : (
          <nav onClick={() => setEditing(path)} aria-label={text("Đường dẫn", "Address")} style={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "nowrap", overflow: "hidden", flex: 1, minWidth: 0, height: 30, padding: "0 8px", borderRadius: 6, border: LINE }}>
            {crumbs.map((crumb, index) => (
              <span
                key={crumb.path}
                onDragOver={(event) => { event.preventDefault(); setDropTarget(crumb.path); }}
                onDragLeave={() => setDropTarget(null)}
                onDrop={dropOn(crumb.path)}
                style={{ display: "inline-flex", alignItems: "center", gap: 2, padding: "2px 4px", borderRadius: 4, background: dropTarget === crumb.path ? HOVER : "transparent" }}
              >
                {index > 0 ? <span aria-hidden="true" className="muted">›</span> : null}
                <button type="button" className="fx-crumb" onClick={(event) => { event.stopPropagation(); navigate(crumb.path); }}>{crumb.label}</button>
              </span>
            ))}
          </nav>
        )}
        <input
          aria-label={text("Tìm trong thư mục", "Search this folder")}
          placeholder={text("Tìm trong thư mục", "Search this folder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 190, height: 30, boxSizing: "border-box", padding: "0 8px", borderRadius: 6, fontSize: 13, border: LINE, background: "transparent", color: "inherit", font: "inherit" }}
        />
      </div>

      {naming ? (
        <div style={{ display: "flex", gap: 8, alignItems: "center", paddingBottom: 6 }}>
          <TextBox aria-label={text("Tên", "Name")} value={naming.value} onChange={(event) => setNaming({ ...naming, value: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter") commitName(); if (event.key === "Escape") setNaming(null); }} autoFocus />
          <Button type="button" size="sm" variant="primary" onClick={commitName}>{text("Lưu", "Save")}</Button>
          <Button type="button" size="sm" variant="secondary" onClick={() => setNaming(null)}>{text("Hủy", "Cancel")}</Button>
        </div>
      ) : null}

      {error ? <p role="alert" style={{ margin: "4px 0", fontWeight: 600, color: "var(--line)" }}>{error}</p> : null}

      {views}

      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 10px", fontSize: 12, borderTop: LINE }}>
        <span>{shown.length} {text("mục", "items")}{selectedRows.length > 0 ? ` · ${selectedRows.length} ${text("đã chọn", "selected")}` : ""}{clip ? ` · ${clip.mode === "cut" ? text("đã cắt", "cut") : text("đã sao chép", "copied")}: ${clip.keys.length}` : ""}</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className="muted">{listing ? `${formatBytes(listing.usage.usedBytes)} / ${formatBytes(listing.usage.quotaBytes)}` : ""}</span>
          {modeButton("details", text("Chi tiết", "Details"))}
          {modeButton("list", text("Danh sách", "List"))}
          {modeButton("small", text("Biểu tượng nhỏ", "Small icons"))}
          {modeButton("large", text("Biểu tượng lớn", "Large icons"))}
        </span>
      </div>
    </div>
  );

  return (
    <div className="fx-root" style={{ display: "flex", gap: 14, height: "100%", minHeight: 420 }}>
      <style>{CSS}</style>
      <aside aria-label={text("Thư mục", "Folders")} style={{ width: 240, flexShrink: 0, overflow: "auto", paddingRight: 10, borderRight: LINE }}>
        {/* keyed by the path: the tree forgets its own open/closed toggles, so it always shows the folder on the right */}
        <TreeView key={path} data={tree} currentKey={path} expandedKeys={expandedKeys} alignLeaves onSelect={(key) => navigate(key)} />
      </aside>
      <section style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        {main}
      </section>

      {modal?.kind === "trash" ? (
        <Dialog label={text("Thùng rác", "Recycle Bin")} wide onClose={() => setModal(null)}>
          <TrashPanel onRestored={() => void load(path)} />
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
            <Button type="button" size="sm" variant="secondary" onClick={() => setModal(null)}>{text("Đóng", "Close")}</Button>
          </div>
        </Dialog>
      ) : null}

      {modal?.kind === "versions" ? (
        <Dialog label={text("Phiên bản trước", "Previous versions")} wide onClose={() => setModal(null)}>
          <VersionsSection path={keyOf(modal.row)} name={modal.row.name} onRestored={() => void load(path)} onClose={() => setModal(null)} />
        </Dialog>
      ) : null}

      {modal?.kind === "share" ? (
        <Dialog label={text("Chia sẻ", "Share")} wide onClose={() => setModal(null)}>
          <ShareSection path={keyOf(modal.row)} name={modal.row.name} onClose={() => setModal(null)} />
        </Dialog>
      ) : null}

      {modal?.kind === "preview" ? (
        <Dialog label={modal.row.name} wide onClose={() => setModal(null)}>
          <p style={{ margin: "0 0 10px", fontSize: 15, fontWeight: 600 }}>{modal.row.name}</p>
          {kindOf(modal.row) === "image" ? <img src={downloadUrl(keyOf(modal.row), area)} alt={modal.row.name} style={{ maxWidth: "100%", maxHeight: "70vh", display: "block", margin: "0 auto" }} /> : null}
          {kindOf(modal.row) === "video" ? <video src={downloadUrl(keyOf(modal.row), area)} controls style={{ maxWidth: "100%", maxHeight: "70vh", display: "block", margin: "0 auto" }} /> : null}
          {kindOf(modal.row) === "audio" ? <audio src={downloadUrl(keyOf(modal.row), area)} controls style={{ width: "100%" }} /> : null}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
            <Button type="button" size="sm" variant="secondary" onClick={() => setModal(null)}>{text("Đóng", "Close")}</Button>
          </div>
        </Dialog>
      ) : null}

      {modal?.kind === "properties" ? (
        <Dialog label={text("Thuộc tính", "Properties")} onClose={() => setModal(null)}>
          <p style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 600 }}>{modal.row.name}</p>
          <table style={{ borderCollapse: "collapse" }}>
            <tbody>
              <tr><td style={{ padding: "3px 12px 3px 0", opacity: 0.7 }}>{text("Loại", "Type")}</td><td>{typeOf(modal.row)}</td></tr>
              <tr><td style={{ padding: "3px 12px 3px 0", opacity: 0.7 }}>{text("Vị trí", "Location")}</td><td>{modal.row.dir}</td></tr>
              <tr><td style={{ padding: "3px 12px 3px 0", opacity: 0.7 }}>{text("Kích thước", "Size")}</td><td>{modal.row.type === "file" ? formatBytes(modal.row.size) : "—"}</td></tr>
              <tr><td style={{ padding: "3px 12px 3px 0", opacity: 0.7 }}>{text("Ngày sửa", "Date modified")}</td><td>{timeOf(modal.row.modifiedAt)}</td></tr>
            </tbody>
          </table>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
            <Button type="button" size="sm" variant="secondary" onClick={() => setModal(null)}>{text("Đóng", "Close")}</Button>
          </div>
        </Dialog>
      ) : null}

      {menu ? <ContextMenu x={menu.x} y={menu.y} label={text("Thao tác", "Actions")} items={menuItems(menu.row)} onClose={() => setMenu(null)} /> : null}
    </div>
  );
}
