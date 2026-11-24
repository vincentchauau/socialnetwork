"use client";

import { useState, useEffect } from "react";
import JsonView from "../elements/JsonView";
import { BORDER, MediaView, THUMB } from "./FileTools";
import Card from "../elements/Card";
import Button from "../elements/Button";
import { BG, FG } from "../lib/theme";
import { fileName, mediaKind, mediaSrc, type MediaKind } from "./crudModel";
import { type ColumnInfo, type Row, type TableInfo, crudTr } from "./crudModel";



const TECHNICAL = [/_id$/, /^password/, /hash/, /token/, /_key$/, /^content_type$/, /^width$/, /^height$/, /^salt$/];
const LONG_TEXT = 60;
const BADGE_NAME = /^(status|state|kind|role|level|category|outcome|winner|method)$/;
const IMAGE_NAME = /^(image|avatar)|_url$/;
const IMAGE_FILE = /\.(jpe?g|png|webp|gif)(\?.*)?$/i;

/** Whether the column is plumbing (a foreign key without a known reference, a hash, a size…) that a person does not need to read. Key columns are never plumbing. */
export function isTechnical(table: TableInfo, column: ColumnInfo): boolean {
  if (table.pk.includes(column.name)) return false;
  if (column.ref) return false;
  return column.secret || column.type === "bytes" || TECHNICAL.some((pattern) => pattern.test(column.name));
}

/** The names of the columns shown when the person has not chosen. */
export function defaultShown(table: TableInfo): string[] {
  return table.columns.filter((column) => !isTechnical(table, column)).map((column) => column.name);
}

/** A date and time as the person's browser writes it, short; what is not a date stays as it is. */
export function formatDateTime(value: unknown): string {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

/** Whether a string is the address of a small picture to show instead of the text. */
export function isImageValue(name: string, value: unknown): value is string {
  if (typeof value !== "string" || !(value.startsWith("/") || /^https?:\/\//i.test(value))) return false;
  if (IMAGE_NAME.test(name) && IMAGE_FILE.test(value)) return true;
  return value.startsWith("/api/") && /image|thumb/i.test(value);
}

/** A stable hue (0-359) for a value: equal values get equal colors in every table and app. */
export const NOWRAP_STYLE = { whiteSpace: "nowrap" } as const;

export function hueOf(value: string): number {
  let hash = 0;
  for (const char of value.toLowerCase()) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % 360;
}

function Badge({ value }: { value: string }) {
  const hue = hueOf(value);
  return (
    <span
      className="sn-dt-badge"
      data-hue={hue}
      style={{ background: `color-mix(in srgb, var(--solid-${1 + (hue % 3)}) 28%, transparent)`, border: `1px solid color-mix(in srgb, var(--solid-${1 + (hue % 3)}) 55%, transparent)` }}
    >
      {value}
    </span>
  );
}

function Expandable({ short, full, title }: { short: string; full: string; title?: string }) {
  const [open, setOpen] = useState(false);
  if (full.length <= LONG_TEXT && !full.includes("\n")) return <span className="sn-dt-text" title={title ?? full}>{full}</span>;
  return (
    <button type="button" className={open ? "sn-dt-expand sn-dt-open" : "sn-dt-expand"} title={`${title ?? full}\n${crudTr(open ? "collapse" : "expand")}`} aria-expanded={open} onClick={() => setOpen(!open)}>
      <span className="sn-dt-expand-text">{open ? full : short}</span>
      <span className="sn-dt-chevron" aria-hidden="true">{open ? "▴" : "▾"}</span>
    </button>
  );
}

const clip = (text: string) => (text.length > LONG_TEXT ? `${text.slice(0, LONG_TEXT)}…` : text.split("\n")[0]);

/** One value of a row, written the way a person reads it. `labels` maps the values of a reference column to their text. */
export function CellView({ column, value, labels, table, row, stamp }: { column: ColumnInfo; value: unknown; labels?: Record<string, string>; table?: TableInfo; row?: Row; stamp?: number }) {
  if (column.secret || column.type === "bytes") return <span>***</span>;
  const isEmpty = value === null || value === undefined || (BADGE_NAME.test(column.name) && value === "");
  if (isEmpty) return <span className="sn-dt-muted" aria-label="null">–</span>;
  if (column.media && table && row) return <MediaCell table={table} column={column} row={row} stamp={stamp} />;
  if (column.type === "bool") return <span aria-label={value ? crudTr("yes") : crudTr("no")} title={value ? crudTr("yes") : crudTr("no")}>{value ? "✓" : "–"}</span>;
  if (column.type === "datetime") return <span title={String(value)}>{formatDateTime(value)}</span>;
  if (column.type === "json") return <JsonCell value={value} />;
  if (column.ref) {
    const label = labels?.[String(value)];
    if (label) return <span className="sn-dt-text" title={crudTr("id_title", { column: column.name, value: String(value) })}>{label}</span>;
  }
  if (BADGE_NAME.test(column.name) && (typeof value === "string" || typeof value === "number")) return <Badge value={String(value)} />;
  if (isImageValue(column.name, value)) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={value} alt="" loading="lazy" title={value} style={{ height: 28, width: 28, objectFit: "cover", borderRadius: 4, verticalAlign: "middle" }} />;
  }
  const text = String(value);
  return <Expandable short={clip(text)} full={text} />;
}




/** A json value, in plain sight in the cell: its keys and values, not a summary and not a dialog. */
function JsonCell({ value }: { value: unknown }) {
  return <JsonView value={value} />;
}

export const KIND_ICON: Record<MediaKind, string> = { image: "🖼", video: "▶", audio: "♪", file: "📄" };

/** A dialog over the page with the media in full size. Escape or a click outside closes it. */
function PreviewDialog({ kind, src, name, onClose }: { kind: MediaKind; src: string; name: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
      style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", padding: 12, background: "color-mix(in srgb, var(--line, #000) 55%, transparent)" }}
    >
      <div role="dialog" aria-modal="true" aria-label={crudTr("preview_title")} style={{ maxWidth: "95vw", maxHeight: "90vh", overflow: "auto", padding: 12, borderRadius: 8, background: "var(--solid-0, #fff)", color: "var(--line, #16181d)", border: BORDER, whiteSpace: "normal" }}>
        <p style={{ margin: "0 0 8px", wordBreak: "break-all" }}>{name}</p>
        <MediaView kind={kind} src={src} name={name} big />
        <div style={{ marginTop: 8, textAlign: "right" }}><button type="button" onClick={onClose}>{crudTr("close")}</button></div>
      </div>
    </div>
  );
}

/** A cell of a media column: a small thumbnail / icon, then the file name only (the full value in the title). Click opens the full-size preview. */
function MediaCell({ table, column, row, stamp }: { table: TableInfo; column: ColumnInfo; row: Row; stamp?: number }) {
  const [open, setOpen] = useState(false);
  const kind = mediaKind(column.media!);
  const value = String(row[column.name] ?? "");
  const src = mediaSrc(table, column, row, stamp);
  const name = fileName(value);
  const text = <span className="sn-dt-text sn-dt-nowrap" title={value}>{name}</span>;
  if (!src) return text;
  if (kind === "file") {
    return <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span aria-hidden="true">{KIND_ICON.file}</span><a href={src} download={name} title={value}>{name}</a></span>;
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <button type="button" data-testid={`media-${column.name}`} aria-label={`${crudTr("preview_open")}: ${name}`} title={crudTr("preview_open")} onClick={() => setOpen(true)} style={{ all: "unset", cursor: "pointer", display: "inline-flex" }}>
        {kind === "image" ? <MediaView kind="image" src={src} name={name} /> : <span aria-hidden="true" style={{ ...THUMB, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>{KIND_ICON[kind]}</span>}
      </button>
      {text}
      {open ? <PreviewDialog kind={kind} src={src} name={name} onClose={() => setOpen(false)} /> : null}
    </span>
  );
}
